import logging
import os


def env(name, default=None, required=False, is_bool=False, is_list=False):
    value = os.environ.get(name)
    if required and not name:
        raise KeyError(f'You need to define the environmental variable "{name}"')
    elif is_list or isinstance(default, (list, set, tuple)):
        convert = type(default) if default is not None else list
        if value is None:
            return convert() if default is None else default
        return convert(map(str.strip, value.split(',')))
    elif is_bool or isinstance(default, bool):
        if value is None:
            return default or False
        return bool(value.lower() in ['1', 'true', 'yes'])
    elif value is None:
        return default
    return value

TELEGRAM_API_TOKEN = env('TELEGRAM_API_TOKEN', required=True)

ADMINS = env('ADMINS', required=True, is_list=True)
CHAT_ID = int(env('CHAT_ID', required=True))

SUFFIX = env('SUFFIX', '')

AUTO_START = env('AUTO', True)
SHOW_CHARACTER_TAG = env('SHOW_CHARACTER_TAG', True)
SHOW_ARTIST_TAG = env('SHOW_ARTIST_TAG', True)
SHOW_ID = env('SHOW_ID', True)

SEARCH_TAGS = env('SEARCH_TAGS', 'rating:safe') # AND filter
POST_TAG_FILTER = env('POST_TAG_FILTER', set()) # OR filter
MAX_TAGS = int(env('MAX_TAGS', 15))
SHOWN_TAGS = env('SHOWN_TAGS', {  # Tags that will always be shown. Other tags will be selected randomly to reach MAX_TAGS
    '1girl', '2girls', '3girls', '4girls', '5girls', '6+girls', 'highres',
    'blue_eyes', 'blonde_hair', 'yuri'
})

RELOAD_INTEVAL = int(env('RELOAD_INTEVAL', 5))  # in min

SERVICE = {
    'name': 'danbooru',
    'url': 'https://danbooru.donmai.us',
    'api': env('DANBOORU_API'),
    'username': env('DANBOORU_USERNAME'),
    'password': env('DANBOORU_PASSWORD'),
}

# {
#     'name': 'safebooru',
#     'url': 'https://safebooru.donmai.us',
#     'api': None,
#     'username': None,
#     'password': None,
# }


# More information about polling and webhooks can be found here:
# https://github.com/python-telegram-bot/python-telegram-bot/wiki/Webhooks
if env('WEBHOOK', True):
    DOMAIN = env('DOMAIN', required=True)
    MODE = {
        'active': 'webhook',  # "webook" or "polling"
        'configuration': {
            'listen': '127.0.0.1',
            'port': 5000,
            'url_path': TELEGRAM_API_TOKEN,
            'url': 'https://%s/%s' % (DOMAIN, TELEGRAM_API_TOKEN),
        },
    }
else:
    MODE = {
        'active': 'polling',
    }

if env('DEBUG', False):
    LOG_LEVEL = logging.DEBUG
else:
    LOG_LEVEL = logging.INFO
