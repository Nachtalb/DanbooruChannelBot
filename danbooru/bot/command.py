import logging
from datetime import timedelta
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import run_async
from telegram.parsemode import ParseMode

from danbooru.bot.animedatabase_utils.danbooru_service import DanbooruService
from danbooru.bot.animedatabase_utils.post import Post
from danbooru.bot.bot import danbooru_bot
from danbooru.bot import settings


class Command:
    is_refreshing = False
    is_manual_refresh = False

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

    @property
    def last_post_id(self) -> int:
        if not self._last_post_id:
            try:
                with open(self.last_post_file) as file_:
                    self._last_post_id = int(file_.read().strip())
            except FileNotFoundError:
                raise ValueError('You have to set a post id in the last_post.txt')
        return self._last_post_id

    @last_post_id.setter
    def last_post_id(self, value: int):
        self._last_post_id = value
        with open(self.last_post_file, mode='w') as file_:
            file_.write(str(self._last_post_id))

    def is_ok(self, post: Post):
        tags = set(post.tag_string.split(' '))
        white_list = set(filter(lambda tag: not tag.startswith('-'), settings.SEARCH_TAGS))
        black_list = set(map(lambda tag: tag.strip('-'), settings.SEARCH_TAGS - white_list))

        if not tags & black_list and tags & white_list == white_list:
            return True
        return False

    def get_posts(self):
        posts = self.service.client.post_list(limit=1)
        latest_post_id = posts[0]['id']

        if self.last_post_id == latest_post_id:
            return []

        for post_id in range(self.last_post_id + 1, latest_post_id + 1):
            try:
                post_dict = self.service.client.post_show(post_id)
                post = Post(post_dict, self.service)
                if not self.is_ok(post):
                    continue
                yield post
            except Exception as error:
                print(error)
                pass

    def to_tags(self, tags: List[str] or str) -> str:
        if isinstance(tags, str):
            tags = map(str.strip, tags.split(' '))
        tag_string = ' '.join(map(lambda tag: f'#{tag}', tags))
        return tag_string.translate(str.maketrans({
            '-': r'_',
            ']': r'_',
            '[': r'_',
            '\'': r'_',
            '\\': r'_',
            '/': r'_',
            '^': r'_',
            '$': r'_',
            '*': r'_',
            '.': r'_',
            '(': r'_',
            ')': r'_',
        }))

    def get_sauce_url(self, post: Post):
        if post.post.get('pixiv_id'):
            return 'https://www.pixiv.net/member_illust.php?mode=medium&illust_id={post.pixiv_id}'
        elif post.post.get('source'):
            return post.source

    def create_post(self, post: Post) -> Tuple[Callable, Dict]:
        tags = set(post.tag_string.split(' '))
        caption = ''
        if settings.SHOWN_TAGS & tags:
            caption = '<b>Tags:</b> ' + self.to_tags(settings.SHOWN_TAGS & tags)

        if settings.SHOW_ARTIST_TAG and post.post.get('tag_string_artist'):
            caption += '\n<b>Artist:</b> ' + self.to_tags(post.tag_string_artist)
        if settings.SHOW_CHARACTER_TAG and post.post.get('tag_string_character'):
            caption += '\n<b>Characters:</b> ' + self.to_tags(post.tag_string_character)

        buttons = [
            [InlineKeyboardButton(text='View on Danbooru', url=post.link)]
        ]

        source = self.get_sauce_url(post)
        if source:
            buttons.append([InlineKeyboardButton(text='Source', url=source)])

        kwargs = {
            'chat_id': settings.CHAT_ID,
            'caption': caption,
            'reply_markup': InlineKeyboardMarkup(buttons),
            'parse_mode': ParseMode.HTML,
        }
        if post.is_image:
            kwargs['photo'] = post.file
            func = danbooru_bot.updater.bot.send_photo
        elif post.file_extension == 'mp4':
            kwargs['video'] = post.file
            func = danbooru_bot.updater.bot.send_video
        elif post.is_gif:
            kwargs['animation'] = post.file
            func = danbooru_bot.updater.bot.send_animation
        else:
            kwargs['document'] = post.file
            func = danbooru_bot.updater.bot.send_document

        return func, kwargs

    def send_posts(self, posts):
        self.is_refreshing = True
        for post in posts:
            if ((self.job and self.job.removed) or (not self.job)) and not self.is_manual_refresh:
                self.logger.info('Scheduled task was stopped while refreshing')
                break

            method, kwargs = self.create_post(post)
            try:
                method(**kwargs)
            except:
                pass
            finally:
                self.last_post_id = post.id
        self.is_refreshing = False

    def refresh(self, *args, is_manual: bool = False):
        if self.is_refreshing:
            self.logger.info('Refresh already running')
            return

        if is_manual:
            self.is_manual_refresh = True

        self.logger.info('Start refresh')
        self.send_posts(self.get_posts())
        self.logger.info('Finished refresh')

    def start_scheduler(self):
        if self.job and not self.job.removed:
            return

        self.logger.info('Starting scheduled job')
        self.job = danbooru_bot.updater.job_queue.run_repeating(self.refresh, interval=timedelta(minutes=5),
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


command = Command()
