import logging
import os

TELEGRAM_API_TOKEN = os.environ['TELEGRAM_API_TOKEN']

ADMINS = os.environ['ADMINS']
CHAT_ID = int(os.environ['CHAT_ID'])

SUFFIX = ''

AUTO_START = True
SHOW_CHARACTER_TAG = True
SHOW_ARTIST_TAG = True
SHOW_ID = True

SEARCH_TAGS = 'rating:safe'  # AND filter
POST_TAG_FILTER = set()      # OR filter
MAX_TAGS = 15
SHOWN_TAGS = {  # Tags that will always be shown. Other tags will be selected randomly to reach MAX_TAGS
    '1girl', '2girls', '3girls', '4girls', '5girls', '6+girls', 'highres',
    'blue_eyes', 'blonde_hair', 'yuri'
}

RELOAD_INTEVAL = 5  # in min

SERVICE = {
    'name': 'danbooru',
    'type': 'danbooru',
    'url': 'https://danbooru.donmai.us',
    'api': os.environ['DANBOORU_API'],
    'username': os.environ['DANBOORU_USERNAME'],
    'password': os.environ['DANBOORU_PASSWORD'],
}
# {
#     'name': 'safebooru',
#     'type': 'danbooru',
#     'url': 'https://safebooru.donmai.us',
#     'api': None,
#     'username': None,
#     'password': None,
# }


# More information about polling and webhooks can be found here:
# https://github.com/python-telegram-bot/python-telegram-bot/wiki/Webhooks
MODE = {
    'active': 'webhook',  # "webook" or "polling"
    'configuration': {
        'listen': '127.0.0.1',
        'port': 5000,
        'url_path': TELEGRAM_API_TOKEN,
        'url': 'https://%s/%s' % (os.environ['DOMAIN'], TELEGRAM_API_TOKEN),
    },
}

LOG_LEVEL = logging.DEBUG
