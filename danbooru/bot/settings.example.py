import logging

TELEGRAM_API_TOKEN = ''

ADMINS = ['@USERNAME']
CHAT_ID = -0

AUTO_START = False
SHOW_CHARACTER_TAG = True
SHOW_ARTIST_TAG = True
SHOW_ID = True

SEARCH_TAGS = 'rating:safe'  # AND filter
POST_TAG_FILTER = set()      # OR filter
MAX_TAGS = 15
SHOWN_TAGS = {  # Tags that will always be shown. Other tags will be selected randomly to reach MAX_TAGS
    '1girl', '2girls', '3girls', '4girls', '5girls', '6+girls', 'highres', 'blue_eyes', 'blonde_hair',
    'loli', 'shota', 'incest', 'yuri', 'yaoi', 'dark_skin', 'nipples',
}

RELOAD_INTEVAL = 5  # in min

SERVICE = {
    'name': 'danbooru',
    'type': 'danbooru',
    'url': 'https://danbooru.donmai.us',
    'api': None,
    'username': None,
    'password': None,
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
    'active': 'polling',  # "webook" or "polling"
    # 'configuration': {
    #     'listen': '127.0.0.1',
    #     'port': 5000,
    #     'url_path': TELEGRAM_API_TOKEN,
    #     'url': 'https://your_domain.tld/%s' % TELEGRAM_API_TOKEN,
    # },
}

LOG_LEVEL = logging.DEBUG
