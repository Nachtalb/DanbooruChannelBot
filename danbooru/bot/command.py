from datetime import timedelta
from io import BytesIO
import json
import logging
from pathlib import Path
from random import sample
import re
from time import time
from typing import Any, Callable, Dict, Generator, Iterable
from urllib.parse import urlparse

from emoji import emojize
from pyvips import Image
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import CallbackContext, MessageHandler
from telegram.ext.utils.promise import Promise
from telegram.files.inputfile import InputFile
from telegram.parsemode import ParseMode
from timeout_decorator import TimeoutError
from yarl import URL

from danbooru.bot import settings
from danbooru.bot.animedatabase_utils.danbooru_service import DanbooruService
from danbooru.bot.animedatabase_utils.post import Post
from danbooru.bot.bot import danbooru_bot


class Tracker(list):
    _tracker_file = Path("tracker.txt")

    def __init__(self):
        self._tracker_file.touch(exist_ok=True)
        self.load()

    def load(self):
        content = self._tracker_file.read_text()
        ids = map(int, content.strip().split())
        super(Tracker, self).__init__(ids)

    def not_implemented(self):
        raise NotImplementedError

    clear = remove = insert = pop = not_implemented

    def append(self, item):
        self.extend([item])

    def extend(self, items):
        super(Tracker, self).extend(items)
        if len(self) > 100:
            items = self[len(self) - 100 :]
            super(Tracker, self).__init__(items)
        self._tracker_file.write_text(" ".join(map(str, self)))


class Command:
    is_refreshing = False
    is_manual_refresh = False
    tracker = Tracker()
    _sub_config = Path("sub_config.json")
    _prepared_post_kwargs = {}
    SAFE_CONFIG_KEYS = {
        "artist",
        "buttons",
        "characters",
        "date_format",
        "id",
        "suffix",
        "tags",
        "time",
        "no_file",
        "direct_button",
        "force_file",
        "explicit_file",
        "questionable_file",
        "debug",
    }
    UNSAFE_CONFIG_KEYS = {"subs"}

    def __init__(self):
        self.service = DanbooruService(**settings.SERVICE)
        self.last_post_file = Path("last_post.txt")
        self._last_post_id = None
        self.logger = logging.getLogger(self.__class__.__name__)

        self.job = None
        if settings.AUTO_START:
            self.start_scheduler()

        self._sub_config.touch()

        danbooru_bot.add_command(
            name="config", func=self.change_config_command_wrapper, admin=False, pass_args=True, run_async=True
        )
        danbooru_bot.add_command(name="sub", func=self.subscribe_command, admin=False, pass_args=True, run_async=True)
        danbooru_bot.add_command(
            name="unsub", func=self.unsubscribe_command, admin=False, pass_args=True, run_async=True
        )
        danbooru_bot.add_command(
            name="gsub", func=self.subscribe_group_command, admin=False, pass_args=True, run_async=True
        )
        danbooru_bot.add_command(
            name="gunsub", func=self.unsubscribe_group_command, admin=False, pass_args=True, run_async=True
        )
        danbooru_bot.add_command(name="refresh", func=self.refresh_command, run_async=True)
        danbooru_bot.add_command(name="start", func=self.start_command, run_async=True)
        danbooru_bot.add_command(name="cancel", func=self.cancel_command, run_async=True)
        danbooru_bot.add_command(name="stop", func=self.stop_command, run_async=True)
        danbooru_bot.add_command(name="ipdb", func=self.ipdb, run_async=True, admin=True)
        danbooru_bot.add_command(name="pdb", func=self.pdb, run_async=True, admin=True)
        danbooru_bot.add_command(MessageHandler, func=self.messagehandler, filters=None, run_async=True)

    @property
    def last_post_id(self) -> int:
        if not self._last_post_id:
            try:
                self._last_post_id = int(self.last_post_file.read_text().strip())
            except FileNotFoundError:
                latest_post = next(iter(self.service.client.post_list(limit=1)), None)
                if latest_post is None:
                    raise ValueError("You have to set a post id in the last_post.txt")
                else:
                    self._last_post_id = latest_post["id"]
                    self.last_post_file.write_text(str(self._last_post_id))
        return self._last_post_id

    @last_post_id.setter
    def last_post_id(self, value: int):
        self._last_post_id = value
        with open(self.last_post_file, mode="w") as file_:
            file_.write(str(self._last_post_id))

    def is_ok(self, post: Post) -> bool:
        try:
            if post.is_banned or post.is_deleted:
                return False
        except KeyError:
            pass

        tags = set(post.tag_string.split(" "))
        white_list = set(filter(lambda tag: not tag.startswith("-"), settings.POST_TAG_FILTER))  # type: ignore
        black_list = set(map(lambda tag: tag.strip("-"), settings.POST_TAG_FILTER - white_list))  # type: ignore

        if not tags & black_list and tags & white_list == white_list:
            return True
        return False

    def _get_posts_by_number_only(self):
        posts = self.service.client.post_list(limit=1)
        if not posts:
            return

        latest_post_id = posts[0]["id"]

        if self.last_post_id == latest_post_id:
            return

        posts = self.service.client.post_list(limit=latest_post_id - self.last_post_id)
        id_post_map = dict(map(lambda post: (post["id"], post), posts))

        for post_id in range(self.last_post_id + 1, latest_post_id + 1):
            try:
                post_dict = id_post_map.get(post_id, self.service.client.post_show(post_id))
                if "id" not in post_dict:
                    self.logger.warning("Skip restricted post")
                    continue
            except Exception as e:
                self.logger.warning(f"Exception during downloading info for post {post_id}")
                self.logger.exception(e)
                continue

            post = Post(post_dict, self.service)
            if time() - post.created_at.timestamp() < settings.GRACE_PERIOD:
                # None of the following posts are older thus we can toss it here
                return
            if not self.is_ok(post):
                continue
            yield post

    def _get_posts_by_search(self):
        posts = self.service.client.post_list(limit=100, tags=settings.SEARCH_TAGS)
        # FIXME: The tracker doesn't seem to be transported over the threads very well by
        # timeout_decorator thus we have to load it again
        self.tracker.load()

        for post_dict in reversed(posts):
            if "id" not in post_dict:
                self.logger.warning("Skip restricted post")
                continue
            if (not settings.LAST_100_TRACK and self.last_post_id >= post_dict["id"]) or (
                settings.LAST_100_TRACK and post_dict["id"] in self.tracker
            ):
                continue

            post = Post(post_dict, self.service)
            if not self.is_ok(post):
                continue
            yield post

    def get_posts(self):
        if settings.SEARCH_TAGS:
            yield from self._get_posts_by_search()
        else:
            yield from self._get_posts_by_number_only()

    def telegram_cleaned_tags(self, tags: Iterable[str] | str) -> list[str]:
        if not isinstance(tags, str):
            tags = " ".join(tags)
        return re.sub("[^_a-zA-Z0-9\\s]", "", tags).split(" ")

    def to_telegram_tags(self, tags: Iterable[str] | str) -> str:
        tags = self.telegram_cleaned_tags(tags)
        return "#" + " #".join(tags)

    def get_sauce_url(self, post: Post) -> str:
        if post.post.get("pixiv_id"):
            return f"https://www.pixiv.net/member_illust.php?mode=medium&illust_id={post.pixiv_id}"
        elif post.post.get("source"):
            return post.source
        return ""

    def get_tags(self, available_tags: set[str]) -> set[str]:
        available_tags = set(available_tags)
        tags = settings.SHOWN_TAGS & available_tags  # type: ignore

        default_amount = settings.MAX_TAGS - len(tags)
        max_amount = len(available_tags - tags)
        fill_amount = default_amount if max_amount >= default_amount else max_amount

        return tags | set(sample(available_tags - tags, k=fill_amount))

    def match_tags(self, source: set, check: set, strict: bool = True) -> bool:
        bad = set([tag[1:] for tag in check if tag.startswith("-")])
        good = set([tag for tag in check if not tag.startswith("-")])

        if source & bad:
            return False
        elif not strict and source & good:
            return True
        elif strict and source & good == good:
            return True
        return False

    def named_source(self, post: Post) -> str | None:
        url = URL(self.get_sauce_url(post))
        if not url.host:
            return None

        title = url.host.rsplit(".", 2)[-2].title()

        if title == "Twitter":
            title += " - @" + url.path.split("/", 2)[1]
        elif title == "Fanbox":
            title += " - " + url.host.split(".")[-3].title()
        elif post.post.get("tag_string_artist"):
            artist = post.tag_string_artist
            title += " - " + artist.title()

        return title

    def create_promise(self, post: Post) -> Promise:
        targets = []
        targets.append(self.create_post(post, settings.CHAT_ID))
        for chat_id, config in self.config.items():
            data = self.create_post(post, int(chat_id), config)
            if data:
                self.logger.debug(f'┃ Post also goes to: {chat_id} with tags {config["subs"]}')
                targets.append(data)

        return Promise(self.send_posts_to_targets, (targets, post.id), {})

    def send_posts_to_targets(self, targets: list[tuple[Callable, dict]], post_id: int):
        try:
            for method, kwargs in targets:
                self.logger.info(f'┃ {method.__name__.replace("_", " ").title()} to {kwargs["chat_id"]}')
                try:
                    method(**kwargs, queued=False)
                except Exception as exc:
                    self.logger.exception(exc)
        finally:
            self.last_post_id = post_id
            if settings.LAST_100_TRACK:
                self.tracker.append(post_id)
            if post_id in self._prepared_post_kwargs:
                del self._prepared_post_kwargs[post_id]

    def create_post(
        self, post: Post, chat_id: int, config: dict = {}, no_file: bool = False, force_file: bool = False
    ) -> tuple[Callable, Dict] | None:
        tags = set(post.tag_string.split(" "))
        caption = ""

        if config:
            extended_tags = tags | set([post.rating_tag])
            extended_tags = extended_tags | set(self.telegram_cleaned_tags(extended_tags))

            for name, check_tags in config.get("subs", {}).items():
                check_tags = set(check_tags)
                if (name == "OR" and self.match_tags(extended_tags, check_tags, False)) or (
                    name != "OR" and self.match_tags(extended_tags, check_tags)
                ):
                    if config.get("debug"):
                        caption += f'<pre>matched with group "{name}"</pre>\n'
                    break
            else:
                return

        if config.get("artist", settings.SHOW_ARTIST_TAG):
            tags = tags - set([post.post.get("tag_string_artist", [])])
        if config.get("characters", settings.SHOW_CHARACTER_TAG):
            tags = tags - set(post.post.get("tag_string_character", []))

        tags = self.get_tags(tags)
        source = self.get_sauce_url(post)
        source_url = URL(source or "")

        if config.get("time", settings.SHOW_DATE):
            caption += "\n<b>Posted at:</b> %s" % post.created_at.strftime(
                config.get("date_format", settings.DATE_FORMAT)
            )
        if config.get("id", settings.SHOW_ID):
            caption += "\n<b>ID:</b> " + str(post.id)
        if config.get("tags", True) and tags:
            caption += "\n<b>Tags:</b> " + self.to_telegram_tags(tags)
        if config.get("artist", settings.SHOW_ARTIST_TAG) and post.post.get("tag_string_artist"):
            caption += "\n<b>Artist:</b> " + self.to_telegram_tags(post.tag_string_artist)
        if config.get("characters", settings.SHOW_CHARACTER_TAG) and post.post.get("tag_string_character"):
            caption += "\n<b>Characters:</b> " + self.to_telegram_tags(post.tag_string_character)
        if config.get("suffix", settings.SUFFIX):
            suffix = config.get("suffix", settings.SUFFIX)
            if "{src}" in suffix or "{namedsrc}" in suffix:
                if source and source_url.host:
                    namedsrc = '<a href="{src}">{name}</a>'.format(src=source, name=self.named_source(post))
                    caption += suffix.format(src=source, namedsrc=namedsrc)
            else:
                caption += suffix

        if config.get("no_file", settings.NO_FILE):
            no_file = True
        if config.get("force_file", settings.FORCE_FILE):
            force_file = True
        if config.get("explicit_file", settings.EXPLICIT_FILE) and post.rating == "e":
            force_file = True
        if config.get("questionable_file", settings.QUESTIONABLE_FILE) and post.rating in "qe":
            force_file = True

        buttons = None
        if config.get("buttons", settings.SHOW_BUTTONS):
            buttons = [[InlineKeyboardButton(text=emojize(":package:"), url=post.link)]]

            if source and URL(source).host:
                source_emojis = {
                    "twitter.com": "bird",
                    "t.co": "bird",
                    "pixiv.net": "P_button",
                }
                emoji = source_emojis.get(re.sub("^www\\.", "", urlparse(source).netloc), "globe_with_meridians")
                buttons[0].append(InlineKeyboardButton(text=emojize(f":{emoji}:"), url=source))

            if config.get("direct_button", settings.DIRECT_BUTTON):
                buttons[0].append(InlineKeyboardButton(text=emojize(":framed_picture:"), url=post.nice_file_url))

            buttons = InlineKeyboardMarkup(buttons)

        kwargs = {
            "chat_id": chat_id,
            "caption": caption,
            "reply_markup": buttons,
            "parse_mode": ParseMode.HTML,
        }

        func, extra_kwargs = self.create_post_file_kwargs(post, force_file=force_file, no_file=no_file)
        kwargs.update(extra_kwargs)

        if no_file:
            kwargs["text"] = kwargs["caption"]
            del kwargs["caption"]
        return func, kwargs

    def create_post_file_kwargs(self, post, force_file=False, no_file=False):
        if post.id in self._prepared_post_kwargs and not force_file and not no_file:
            return self._prepared_post_kwargs[post.id]

        post.file.seek(0)
        file = InputFile(post.file, filename=f"{post.id}.{post.file_extension}")
        kwargs = {}
        if force_file:
            self.logger.info(f"┏ {post.id}: Preparing document as {post.file_extension}")
            kwargs["document"] = file
            func = danbooru_bot.updater.bot.send_document
            return func, kwargs
        elif no_file:
            self.logger.info(f"┏ {post.id}: Forced no file")
            func = danbooru_bot.updater.bot.send_message
            return func, kwargs
        elif post.is_image:
            width, height = post.image_width, post.image_height
            self.logger.info(f"┏ {post.id}: Preparing photo")
            if post.file_size > 10 * 1024**2 or width + height > 10000:
                post.file.seek(0)
                image = Image.new_from_buffer(post.file.read(), "")

                while True:
                    while width + height > 10000:
                        width, height = int(width * 0.75), int(height * 0.75)

                    if (scale := width / image.width) != 1:  # type: ignore
                        image = image.resize(scale)  # type: ignore
                        self.logger.info(f"┃ Resizing to a scale of {scale:.2f} [{image.width}x{image.height}]")

                    with BytesIO() as out:
                        out.write(image.write_to_buffer(".jpg"))  # type: ignore
                        out.seek(0)
                        new_length = len(out.read())
                        if new_length > 10 * 1024**2:
                            image = image.resize(0.9)  # type: ignore
                            continue
                        self.logger.info(
                            f"┃ Reduced file size from {post.file_size / 1024**2:.2f}Mb to {new_length / 1024**2:.2f}Mb"
                        )
                        out.seek(0)
                        file = InputFile(out, filename=f"{post.id}.jpg")
                    break

            kwargs["photo"] = file
            func = danbooru_bot.updater.bot.send_photo
        elif post.is_gif or (post.file_extension == "mp4" and not post.has_audio):
            self.logger.info(f"┏ {post.id}: Preparing gif")
            kwargs.update(
                {
                    "animation": file,
                    "duration": post.video.duration if post.video else None,
                    "height": post.image_height,
                    "width": post.image_width,
                    "thumb": post.thumbnail,
                }
            )
            func = danbooru_bot.updater.bot.send_animation
        elif post.file_extension == "mp4":
            self.logger.info(f"┏ {post.id}: Preparing video")
            kwargs.update(
                {
                    "video": file,
                    "duration": post.video.duration,
                    "height": post.image_height,
                    "width": post.image_width,
                    "supports_streaming ": True,
                }
            )
            func = danbooru_bot.updater.bot.send_video
        else:
            self.logger.info(f"┏ {post.id}: Preparing document as {post.file_extension}")
            kwargs["document"] = file
            func = danbooru_bot.updater.bot.send_document

        self._prepared_post_kwargs[post.id] = [func, kwargs]
        return func, kwargs

    # @timeout(300, use_signals=False)
    def send_posts(self, posts):
        if self.is_refreshing:
            return
        self.is_refreshing = True
        for post in posts:
            if not self.is_refreshing:
                self.logger.info("Early termination")
                return

            if ((self.job and self.job.removed) or (not self.job)) and not self.is_manual_refresh:
                self.logger.info("Scheduled task was stopped while refreshing")
                break

            try:
                post.prepare()
                promise = self.create_promise(post)
                danbooru_bot.updater.bot._msg_queue(promise, True)  # type: ignore
                promise.result()
                self.logger.info("┗━━")
            except Exception as e:
                self.logger.exception(e)
        self.is_refreshing = False

    def refresh(self, *args, is_manual: bool = False):
        if self.is_refreshing:
            self.logger.info("Refresh already running")
            return

        if is_manual:
            self.is_manual_refresh = True

        self.logger.info("Start refresh")
        try:
            self.send_posts(self.get_posts())
        except TimeoutError:
            self.logger.info("Refresh took too long and was aborted")
        finally:
            self.is_refreshing = False
        self.logger.info("Finished refresh")

    def start_scheduler(self):
        if self.job and not self.job.removed:
            return

        self.logger.info("Starting scheduled job")
        self.job = danbooru_bot.updater.job_queue.run_repeating(
            self.refresh, interval=timedelta(minutes=settings.RELOAD_INTEVAL), first=1, name="danbooru_refresh"
        )

    def stop_refresh(self, is_manual: bool = False, remove: bool = True):
        self.is_refreshing = False

        if is_manual:
            self.logger.info("Stop manual refresh")
            self.is_manual_refresh = False
        elif not remove:
            self.logger.info("Cancel current refresh")
        else:
            if not self.job or self.job.removed:
                return
            self.logger.info("Stop scheduled refresh")
            self.job.schedule_removal()

    @property
    def config(self) -> dict:
        return json.loads(self._sub_config.read_text() or "{}")

    @config.setter
    def config(self, value: dict):
        self._sub_config.write_text(json.dumps(value, indent=4, sort_keys=True))

    def change_config(self, chat_id: int or str, update: dict):
        if int(chat_id) == settings.CHAT_ID:
            return {}
        self._config_set_default(chat_id)
        config = self.config
        key = str(chat_id)
        config[key].update(update)
        self.config = config
        return config[key]

    def _config_set_default(self, chat_id: int or str):
        if int(chat_id) == settings.CHAT_ID:
            return
        config = self.config
        if not config.get(str(chat_id)):
            config[str(chat_id)] = {
                "time": False,
                "artist": False,
                "id": False,
                "tags": False,
                "characters": False,
                "suffix": "\n{namedsrc}\nPowered by @danbooru_dump",
                "buttons": False,
                "direct_button": False,
                "subs": {"OR": []},
                "force_file": False,
                "no_file": False,
            }
            self.config = config

    def config_set_value(self, chat_id: int or str, key: str, value: Any):
        if int(chat_id) == settings.CHAT_ID:
            return
        self.change_config(chat_id, {key: value})

    def config_get_value(self, chat_id: int or str, key: str = None, default: Any = None):
        if int(chat_id) == settings.CHAT_ID:
            return {}
        self._config_set_default(chat_id)
        result = self.config[str(chat_id)]
        return result.get(key, default) if key else result

    # # # # # # # # #
    # USER COMMANDS #
    # # # # # # # # #

    def print_config(self, update: Update, key: str = None, prefix: str = None):
        message, user, chat = update.effective_message, update.effective_user, update.effective_chat
        self.logger.info(f'## {user.name} [{user.link or "-"}] changed config of "{chat.title}{"@" + chat.username if chat.username else ""}" [{chat.id}]')  # type: ignore

        config = self.config_get_value(chat.id, key)  # type: ignore
        if isinstance(config, list):
            config = ", ".join(config)
        elif isinstance(config, dict):
            config = json.dumps(config, indent=4, sort_keys=True)

        reply = prefix + ": " if prefix else ""
        reply += key + "=" if key else ""
        reply = reply.replace("_", "\\_")
        reply += f"`{config}`"

        self.logger.info("## " + reply)
        message.reply_markdown(reply)  # type: ignore

    def subscribe_command(self, update: Update, context: CallbackContext):
        args = context.args or []
        chat_id = update.message.chat.id
        if args:
            tags = set(map(lambda tag: tag.strip("#"), args))
            sub_config = self.config_get_value(chat_id, "subs", {})
            old_tags = set(sub_config.get("OR", []))
            sub_config["OR"] = list(old_tags | tags)
            self.config_set_value(chat_id, "subs", sub_config)

        self.print_config(update, "subs")

    def unsubscribe_command(self, update: Update, context: CallbackContext):
        args = context.args or []
        chat_id = update.message.chat.id
        if args:
            tags = set(map(lambda tag: tag.strip("#"), args))
            sub_config = self.config_get_value(chat_id, "subs", {})
            old_tags = set(sub_config.get("OR", []))
            sub_config["OR"] = list(old_tags - tags)
            self.config_set_value(chat_id, "subs", sub_config)

        self.print_config(update, "subs")

    def subscribe_group_command(self, update: Update, context: CallbackContext):
        args = context.args or []
        chat_id = update.message.chat.id
        if not args:
            self.print_config(update, "subs")
        if len(args) == 1:
            group = args[0]
            config = ", ".join(self.config_get_value(chat_id, "subs").get(group, []))
            if not config:
                update.message.reply_markdown(f"No group with the name `{group}` exists")
            else:
                update.message.reply_markdown(f"`{group}`=`{config}`")
        elif len(args) > 1:
            group = args[0]
            tags = set(map(lambda tag: tag.strip("#"), args[1:]))
            config = self.config_get_value(chat_id, "subs", {})
            old = set(config.get(group, []))
            config[group] = list(old | tags)
            self.config_set_value(chat_id, "subs", config)
            update.message.reply_markdown(f'`{group}`=`{", ".join(config[group])}`')

    def unsubscribe_group_command(self, update: Update, context: CallbackContext):
        args = context.args or []
        chat_id = update.message.chat.id
        if not args:
            self.print_config(update, "subs")
        if len(args) == 1:
            group = args[0]
            config = self.config_get_value(chat_id, "subs")
            if group in config:
                del config[group]
                self.config_set_value(chat_id, "subs", config)
                update.message.reply_markdown(f"`{group}` was removed")
            else:
                update.message.reply_markdown(f"`{group}` does not exist")
        elif len(args) > 1:
            group = args[0]
            tags = set(map(lambda tag: tag.strip("#"), args[1:]))
            config = self.config_get_value(chat_id, "subs", {})
            old = set(config.get(group, []))
            config[group] = list(old - tags)
            if not config[group]:
                del config[group]
                update.message.reply_markdown(f"`{group}` was removed due to being empty")
            else:
                update.message.reply_markdown(f'`{group}`=`{", ".join(config[group])}`')
            self.config_set_value(chat_id, "subs", config)

    def change_config_command_wrapper(self, update: Update, context: CallbackContext):
        self.change_config_command(update, context.args or [])

    def change_config_command(self, update: Update, args: list[str]):
        if len(args) == 1:
            return self.print_config(update, args[0])
        elif args and args[0] in self.UNSAFE_CONFIG_KEYS:
            return update.message.reply_markdown(f"`{args[0]}` cannot be changed")
        elif args and args[0] not in self.SAFE_CONFIG_KEYS:
            return update.message.reply_markdown(f"`{args[0]}` cannot be set")
        elif len(args) > 1:
            value = " ".join(args[1:]).replace("\\n", "\n")
            if value.lower() in ["true", "yes"]:
                value = True
            elif value.lower() in ["false", "no"]:
                value = False
            elif value in ["''", '""']:
                value = ""
            elif value.lower() != "nan":
                try:
                    value = float(value)
                except ValueError:
                    pass

            self.config_set_value(update.message.chat.id, args[0], value)
        self.print_config(update, args[0] if args else None)

    def refresh_command(self, update: Update, context: CallbackContext):
        if self.is_refreshing:
            update.message.reply_text("Refresh already running")
            return

        update.message.reply_text("Start refresh")
        self.refresh(is_manual=True)
        update.message.reply_text("Finished refresh")

    def start_command(self, update: Update, context: CallbackContext):
        if self.job and not self.job.removed:
            update.message.reply_text("Job already exists")
            return

        update.message.reply_text("Starting job")
        self.start_scheduler()

    def stop_command(self, update: Update, context: CallbackContext):
        manual = False
        if self.is_manual_refresh:
            manual = True
            update.message.reply_text("Refresh was stopped")
        else:
            if not self.job or self.job.removed:
                update.message.reply_text("Job already removed")
                return
            update.message.reply_text("Job scheduled for removal")
        self.stop_refresh(is_manual=manual)

    def cancel_command(self, update: Update, context: CallbackContext):
        if not self.is_refreshing:
            return update.message.reply_text("No running refresh")

        self.stop_refresh(self.is_manual_refresh, remove=False)
        update.message.reply_text("Current refresh was cancelled")

    def messagehandler(self, update: Update, context: CallbackContext):
        message = update.effective_message
        if not message:
            return
        elif message.text.startswith("/id"):
            return self.id(message)
        elif message.text.lower() == "r":
            message.delete()
            if not self.is_refreshing:
                self.refresh(is_manual=True)
            return

        args = message.text.lstrip("/").split()
        args[0] = args[0].lower()
        if message.text.startswith("/") and args[0] in self.SAFE_CONFIG_KEYS | self.UNSAFE_CONFIG_KEYS:
            self.change_config_command(update, args)

    def id(self, message: Message):
        info = {
            "chat_id": message.chat.id,
            "message_id": message.message_id,
            "user": "-",
        }

        user = message.from_user
        if user:
            info["user"] = f"@{user.username}" or f"{user.first_name} {user.last_name}"

        message.reply_text(json.dumps(info, indent=2))

    def pdb(self, update: Update, context: CallbackContext):
        __import__("pdb").set_trace()

    def ipdb(self, update: Update, context: CallbackContext):
        __import__("ipdb").set_trace()


command = Command()
