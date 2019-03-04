import logging

TELEGRAM_API_TOKEN = ''

ADMINS = ['@USERNAME']
CHAT_ID = -0

AUTO_START = False
SHOW_CHARACTER_TAG = True
SHOW_ARTIST_TAG = True

SEARCH_TAGS = set()
SHOWN_TAGS = {  # Based on https://www.gwern.net/Danbooru2018 + a few additional
    '1girl', 'solo', 'long_hair', 'highres', 'breasts', 'blush', 'short_hair', 'smile', 'multiple_girls', 'open_mouth',
    'looking_at_viewer', 'blue_eyes', 'blonde_hair', 'touhou', 'brown_hair', 'skirt', 'hat', 'thighhighs', 'black_hair',
    'loli', 'shota', 'incest', 'yuri', 'yaoi', 'dark_skin', 'nipples',
}

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
