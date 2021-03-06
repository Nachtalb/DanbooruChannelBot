import logging
import json
import re
from datetime import timedelta, datetime
from io import BytesIO
from pathlib import Path
from random import sample
from typing import Callable, Collection, Dict, List, Set, Tuple
from urllib.parse import urlparse

from PIL import Image
from emoji import emojize
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import run_async, MessageHandler
from telegram.files.inputfile import InputFile
from telegram.parsemode import ParseMode
from timeout_decorator import timeout, TimeoutError

from danbooru.bot import settings
from danbooru.bot.animedatabase_utils.danbooru_service import DanbooruService
from danbooru.bot.animedatabase_utils.post import Post
from danbooru.bot.bot import danbooru_bot


class Tracker(list):
    _tracker_file = Path('tracker.txt')

    def __init__(self):
        self._tracker_file.touch(exist_ok=True)
        self.load()

    def load(self):
        content = self._tracker_file.read_text()
        ids = map(int, content.strip().split())
        super(Tracker, self).__init__(ids)

    def not_implemnted(self):
        raise NotImplementedError

    clear = remove = insert = pop = not_implemnted

    def append(self, item):
        self.extend([item])

    def extend(self, items):
        super(Tracker, self).extend(items)
        if len(self) > 100:
            items = self[len(self) - 100:]
            super(Tracker, self).__init__(items)
        self._tracker_file.write_text(' '.join(map(str, self)))


class Command:
    is_refreshing = False
    is_manual_refresh = False
    tracker = Tracker()

    def __init__(self):
        self.service = DanbooruService(**settings.SERVICE)
        self.last_post_file = Path('last_post.txt')
        self._last_post_id = None
        self.logger = logging.getLogger(self.__class__.__name__)

        self.job = None
        if settings.AUTO_START:
            self.start_scheduler()

        danbooru_bot.add_command(name='refresh', func=self.refresh_command)
        danbooru_bot.add_command(name='start', func=self.start_command)
        danbooru_bot.add_command(name='stop', func=self.stop_command)
        danbooru_bot.add_command(MessageHandler, func=self.id, filters=None)

    @property
    def last_post_id(self) -> int:
        if not self._last_post_id:
            try:
                self._last_post_id = int(self.last_post_file.read_text().strip())
            except FileNotFoundError:
                latest_post = next(iter(self.service.client.post_list(limit=1)), None)
                if latest_post is None:
                    raise ValueError('You have to set a post id in the last_post.txt')
                else:
                    self._last_post_id = latest_post['id']
                    self.last_post_file.write_text(str(self._last_post_id))
        return self._last_post_id

    @last_post_id.setter
    def last_post_id(self, value: int):
        self._last_post_id = value
        with open(self.last_post_file, mode='w') as file_:
            file_.write(str(self._last_post_id))

    def is_ok(self, post: Post):
        try:
            if post.is_banned or post.is_deleted:
                return False
        except KeyError:
            pass

        tags = set(post.tag_string.split(' '))
        white_list = set(filter(lambda tag: not tag.startswith('-'), settings.POST_TAG_FILTER))
        black_list = set(map(lambda tag: tag.strip('-'), settings.POST_TAG_FILTER - white_list))

        if not tags & black_list and tags & white_list == white_list:
            return True
        return False

    def _get_posts_by_number_only(self):
        posts = self.service.client.post_list(limit=1)
        if not posts:
            return

        id_post_map = dict(map(lambda post: (post['id'], post), posts))

        latest_post_id = posts[0]['id']

        if self.last_post_id == latest_post_id:
            return

        for post_id in range(self.last_post_id + 1, latest_post_id + 1):
            try:
                post_dict = id_post_map.get(post_id, self.service.client.post_show(post_id))
                if 'id' not in post_dict:
                    self.logger.warning('Skip restricted post')
                    continue
            except Exception as e:
                self.logger.warning(f'Exception during downloading info for post {post_id}')
                self.logger.exception(e)
                continue

            post = Post(post_dict, self.service)
            if not self.is_ok(post):
                continue
            yield post

    def _get_posts_by_search(self):
        posts = self.service.client.post_list(limit=100, tags=settings.SEARCH_TAGS)
        # FIXME: The tracker doesn't seem to be transported over the threads very well by
        # timeout_decorator thus we have to load it again
        self.tracker.load()

        for post_dict in reversed(posts):
            if 'id' not in post_dict:
                self.logger.warning('Skip restricted post')
                continue
            if ((not settings.LAST_100_TRACK and self.last_post_id >= post_dict['id'])
                or (settings.LAST_100_TRACK and post_dict['id'] in self.tracker)):
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

    def to_telegram_tags(self, tags: List[str] or str) -> str:
        if not isinstance(tags, str):
            tags = ' '.join(tags)

        tags = re.sub('[^_a-zA-Z0-9\s]', '', tags)
        return '#' + re.sub(' ', ' #', tags)

    def get_sauce_url(self, post: Post):
        if post.post.get('pixiv_id'):
            return f'https://www.pixiv.net/member_illust.php?mode=medium&illust_id={post.pixiv_id}'
        elif post.post.get('source'):
            return post.source

    def get_tags(self, available_tags: Collection[str]) -> Set[str]:
        available_tags = set(available_tags)
        tags = settings.SHOWN_TAGS & available_tags

        default_amount = settings.MAX_TAGS - len(tags)
        max_amount = len(available_tags - tags)
        fill_amount = default_amount if max_amount >= default_amount else max_amount

        return tags | set(sample(available_tags - tags, k=fill_amount))

    def create_post(self, post: Post) -> Tuple[Callable, Dict]:
        tags = set(post.tag_string.split(' '))
        if settings.SHOW_ARTIST_TAG:
            tags = tags - set([post.post.get('tag_string_artist', [])])
        if settings.SHOW_CHARACTER_TAG:
            tags = tags - set(post.post.get('tag_string_character', []))

        tags = self.get_tags(tags)
        caption = ''

        if settings.SHOW_DATE:
            caption += '\n<b>Posted at:</b> %s' % datetime.fromisoformat(post.created_at).strftime(settings.DATE_FORMAT)
        if settings.SHOW_ID:
            caption += '\n<b>ID:</b> ' + str(post.id)
        if tags:
            caption += '\n<b>Tags:</b> ' + self.to_telegram_tags(tags)
        if settings.SHOW_ARTIST_TAG and post.post.get('tag_string_artist'):
            caption += '\n<b>Artist:</b> ' + self.to_telegram_tags(post.tag_string_artist)
        if settings.SHOW_CHARACTER_TAG and post.post.get('tag_string_character'):
            caption += '\n<b>Characters:</b> ' + self.to_telegram_tags(post.tag_string_character)
        if settings.SUFFIX:
            caption += settings.SUFFIX

        buttons = None
        if settings.SHOW_BUTTONS:
            buttons = [
                [InlineKeyboardButton(text=emojize(':package:'), url=post.link)]
            ]

            source = self.get_sauce_url(post)
            if source:
                source_emojis = {
                    'twitter.com': 'bird',
                    't.co': 'bird',
                    'pixiv.net': 'P_button',
                }
                emoji = source_emojis.get(re.sub('^www\\.', '', urlparse(source).netloc), 'globe_with_meridians')
                buttons[0].append(InlineKeyboardButton(text=emojize(f':{emoji}:'), url=source))

            buttons = InlineKeyboardMarkup(buttons)

        kwargs = {
            'chat_id': settings.CHAT_ID,
            'caption': caption,
            'reply_markup': buttons,
            'parse_mode': ParseMode.HTML,
        }
        file = InputFile(post.file, filename=f'{post.id}.{post.file_extension}')
        if post.is_image:
            if post.file_size > 10000000:
                self.logger.info(f'Resizing photo [{post.id}]')
                image = Image.open(post.file)
                resized_image = image.resize((image.width // 2, image.height // 2))
                with BytesIO() as out:
                    resized_image.save(out, format='PNG')
                    out.seek(0)
                    file = InputFile(out, filename=f'{post.id}.png')
                image.close()
                resized_image.close()
            self.logger.info('Send photo [%d]', post.id)
            kwargs['photo'] = file
            func = danbooru_bot.updater.bot.send_photo
        elif post.is_gif or (post.file_extension == 'mp4' and not post.has_audio):
            self.logger.info('Send gif [%d]', post.id)
            kwargs.update({
                'animation': file,
                'duration': post.video.duration if post.video else None,
                'height': post.image_height,
                'width': post.image_width,
                'thumb': post.thumbnail,
            })
            func = danbooru_bot.updater.bot.send_animation
        elif post.file_extension == 'mp4':
            self.logger.info('Send video [%d]', post.id)
            kwargs.update({
                'video': file,
                'duration': post.video.duration,
                'height': post.image_height,
                'width': post.image_width,
                'supports_streaming ': True,
            })
            func = danbooru_bot.updater.bot.send_video
        else:
            self.logger.info('Send document [%d] - %s', post.id, post.file_extension)
            kwargs['document'] = file
            func = danbooru_bot.updater.bot.send_document

        return func, kwargs

    @timeout(300, use_signals=False)
    def send_posts(self, posts):
        self.is_refreshing = True
        for post in posts:
            if ((self.job and self.job.removed) or (not self.job)) and not self.is_manual_refresh:
                self.logger.info('Scheduled task was stopped while refreshing')
                break

            post.prepare()
            method, kwargs = self.create_post(post)
            try:
                method(**kwargs, timeout=300)
            except Exception as e:
                self.logger.exception(e)
            finally:
                self.last_post_id = post.id
                if settings.LAST_100_TRACK:
                    self.tracker.append(post.id)
        self.is_refreshing = False

    def refresh(self, *args, is_manual: bool = False):
        if self.is_refreshing:
            self.logger.info('Refresh already running')
            return

        if is_manual:
            self.is_manual_refresh = True

        self.logger.info('Start refresh')
        try:
            self.send_posts(self.get_posts())
        except TimeoutError:
            self.logger.info('Refresh took too long and was aborted')
        finally:
            self.is_refreshing = False
        self.logger.info('Finished refresh')

    def start_scheduler(self):
        if self.job and not self.job.removed:
            return

        self.logger.info('Starting scheduled job')
        self.job = danbooru_bot.updater.job_queue.run_repeating(self.refresh, interval=timedelta(minutes=settings.RELOAD_INTEVAL),
                                                                first=0, name='danbooru_refresh')

    def stop_refresh(self, is_manual: bool = False):
        if is_manual:
            self.logger.info('Stop manual refresh')
            self.is_manual_refresh = False
        else:
            if not self.job or self.job.removed:
                return
            self.logger.info('Stop scheduled refresh')
            self.job.schedule_removal()

    # # # # # # # # #
    # USER COMMANDS #
    # # # # # # # # #

    @run_async
    def refresh_command(self, bot: Bot, update: Update):
        if self.is_refreshing:
            update.message.reply_text('Refresh already running')
            return

        update.message.reply_text('Start refresh')
        self.refresh(is_manual=True)
        update.message.reply_text('Finished refresh')

    @run_async
    def start_command(self, bot: Bot = None, update: Update = None):
        if self.job and not self.job.removed:
            update.message.reply_text('Job already exists')
            return

        update.message.reply_text('Starting job')
        self.start_scheduler()

    @run_async
    def stop_command(self, bot: Bot = None, update: Update = None):
        manual = False
        if self.is_manual_refresh:
            manual = True
            update.message.reply_text('Refresh was stopped')
        else:
            if not self.job or self.job.removed:
                update.message.reply_text('Job already removed')
                return
            update.message.reply_text('Job scheduled for removal')
        self.stop_refresh(is_manual=manual)

    @run_async
    def id(self, bot: Bot = None, update: Update = None):
        message = update.effective_message
        if message.text != '/id':
            return

        info = {
            'chat_id': message.chat.id,
            'message_id': message.message_id,
        }

        user = message.from_user
        if user:
            info['user'] = f'@{user.username}' or f'{user.first_name} {user.last_name}'

        message.reply_text(json.dumps(info, indent=2))

command = Command()
