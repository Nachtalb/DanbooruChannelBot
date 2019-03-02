import logging
from datetime import timedelta
from pathlib import Path
from typing import Callable, Dict, Tuple, List

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Job, run_async
from telegram.parsemode import ParseMode

from danbooru.bot.animedatabase_utils.danbooru_service import DanbooruService
from danbooru.bot.animedatabase_utils.post import Post
from danbooru.bot.bot import danbooru_bot
from danbooru.bot.settings import CHAT_ID, SEARCH_TAGS, SERVICE, SHOWN_TAGS, SHOW_ARTIST_TAG, SHOW_CHARACTER_TAG


class Command:
    is_refreshing = False

    def __init__(self):
        self.service = DanbooruService(**SERVICE)
        self.last_post_file = Path('last_post.txt')
        self._last_post_id = None
        self.logger = logging.getLogger(self.__class__.__name__)

        self.job = None
        self.start_scheduler()

        danbooru_bot.add_command(name='refresh', func=self.refresh_command)
        danbooru_bot.add_command(name='start', func=self.start_scheduler)
        danbooru_bot.add_command(name='stop', func=self.stop_scheduler)

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
        white_list = set(filter(lambda tag: not tag.startswith('-'), SEARCH_TAGS))
        black_list = set(map(lambda tag: tag.strip('-'), SEARCH_TAGS - white_list))

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
        tag_string = ' '.join(map(lambda tag: f'#{tag}' , tags))
        return tag_string.translate(str.maketrans({
            '-':  r'_',
            ']':  r'_',
            '[':  r'_',
            '\\': r'_',
            '/': r'_',
            '^':  r'_',
            '$':  r'_',
            '*':  r'_',
            '.':  r'_',
            '(':  r'_',
            ')':  r'_',
        }))

    def create_post(self, post: Post) -> Tuple[Callable, Dict]:
        tags = set(post.tag_string.split(' '))
        caption = ''
        if SHOWN_TAGS & tags:
            caption = '<b>Tags:</b> ' + self.to_tags(SHOWN_TAGS & tags)

        if SHOW_ARTIST_TAG and post.post.get('tag_string_artist'):
            caption += '\n<b>Artist:</b> ' + self.to_tags(post.tag_string_artist)
        if SHOW_CHARACTER_TAG and post.post.get('tag_string_character'):
            caption += '\n<b>Characters:</b> ' + self.to_tags(post.tag_string_character)

        kwargs = {
            'chat_id': CHAT_ID,
            'caption': caption,
            'reply_markup': InlineKeyboardMarkup([[InlineKeyboardButton(text='View on Danbooru', url=post.link)]]),
            'parse_mode': ParseMode.HTML,
        }
        if post.is_image:
            kwargs['photo'] = post.file
            func = danbooru_bot.updater.bot.send_photo
        elif post.is_gif:
            kwargs['video'] = post.file
            func = danbooru_bot.updater.bot.send_video
        elif post.is_video:
            kwargs['animation'] = post.file
            func = danbooru_bot.updater.bot.send_animation
        else:
            kwargs['document'] = post.file
            func = danbooru_bot.updater.bot.send_document

        return func, kwargs

    def send_posts(self, posts):
        self.is_refreshing = True
        for post in posts:
            if self.job and self.job.removed:
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

    @run_async
    def refresh_command(self, bot: Bot, update: Update):
        if self.is_refreshing:
            update.message.reply_text('Refresh already running')
            return

        update.message.reply_text('Start refresh')
        self.refresh(bot, update)
        update.message.reply_text('Finished refresh')

    def refresh(self, bot: Bot = None, update: Update or Job = None):
        if self.is_refreshing:
            self.logger.info('Refresh already running')
            return

        self.logger.info('Start refresh')
        self.send_posts(self.get_posts())
        self.logger.info('Finished refresh')

    @run_async
    def start_scheduler(self, bot: Bot = None, update: Update = None):
        if self.job and not self.job.removed:
            if update and update.message:
                update.message.reply_text('Job already created')
            return

        self.job = danbooru_bot.updater.job_queue.run_repeating(self.refresh, interval=timedelta(minutes=5),
                                                                first=0, name='danbooru_refresh')
        self.logger.info('Job started')
        if update and update.message:
            update.message.reply_text('Job created')
    @run_async
    def stop_scheduler(self, bot: Bot = None, update: Update = None):
        if not self.job or self.job.removed:
            if update and update.message:
                update.message.reply_text('Job already removed')
            return

        self.job.schedule_removal()

        self.logger.info('Job removed')
        if update and update.message:
            update.message.reply_text('Job scheduled for removal')


command = Command()
