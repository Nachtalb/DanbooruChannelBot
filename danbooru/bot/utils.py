import logging
from copy import deepcopy

from telegram import Bot, ParseMode, Update
from telegram.ext import run_async

from danbooru.bot import settings
from danbooru.bot.bot import danbooru_bot


class Utils:
    settings_whitelist = [
        'LOG_LEVEL',
        'SHOWN_TAGS',
        'SEARCH_TAGS',
        'SHOW_ARTIST_TAG',
        'SHOW_CHARACTER_TAG',
        'CHAT_ID',
        'ADMINS',
    ]

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

        danbooru_bot.add_command(name='chat', func=self.get_chat_command)
        danbooru_bot.add_command(name='settings', func=self.runtime_settings_command)

    @run_async
    def get_chat_command(self, bot: Bot, update: Update):
        chat = bot.get_chat(settings.CHAT_ID)
        text = chat.link or chat.title
        update.message.reply_text(f'Chat: {text} -> `{chat.id}`', parse_mode=ParseMode.MARKDOWN)

    @run_async
    def runtime_settings_command(self, bot: Bot, update: Update):
        parts = list(filter(None, update.message.text.split(' ')[1:]))
        setting, value, action = None, None, None
        try:
            if len(parts) == 2:
                setting, value = parts
            elif len(parts) == 3:
                setting, value, action = parts
            else:
                raise ValueError

            if not settings or not value or (action and action not in ['+', '-']):
                raise ValueError
        except ValueError:
            update.message.reply_text('Use like this\n/settings <SETTING_NAME> <NEW_VALUE> <- or + if list>')
            return

        if not hasattr(settings, setting) or setting not in self.settings_whitelist:
            update.message.reply_text('Setting not found')
            return

        old_value = getattr(settings, setting, None)
        if isinstance(old_value, (list, set, tuple)):
            new_value = list(deepcopy(old_value))
            if action == '+':
                new_value.append(value)
                action_name = 'added'
            elif action == '-' and value in new_value:
                new_value.remove(value)
                action_name = 'removed'
            else:
                update.message.reply_text('Action not defined')
                return

            if isinstance(old_value, tuple):
                new_value = tuple(new_value)
            elif isinstance(old_value, set):
                new_value = set(new_value)

            setattr(settings, setting, new_value)
            update.message.reply_text(f'Setting `{setting}` was changed: {action_name} `{value}` in `{old_value}`',
                                      parse_mode=ParseMode.MARKDOWN)
        else:
            setattr(settings, setting, value)
            update.message.reply_text(f'Setting `{setting}` was changed from `{old_value}` to `{value}`',
                                      parse_mode=ParseMode.MARKDOWN)


utils = Utils()
