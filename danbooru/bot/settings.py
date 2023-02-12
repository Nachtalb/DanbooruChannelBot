import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env")


def env(name, default=None, required=False, is_bool=False, is_list=False):
    value = os.environ.get(name)
    if required and not name:
        raise KeyError(f'You need to define the environmental variable "{name}"')
    elif is_list or isinstance(default, (list, set, tuple)):
        convert = type(default) if default is not None else list
        if not value:
            return convert() if default is None else default
        return convert(map(str.strip, value.split(",")))
    elif is_bool or isinstance(default, bool):
        if value is None:
            return default or False
        return bool(value.lower() in ["1", "true", "yes"])
    elif value is None:
        return default
    return value


if _dir := os.environ.get("CONFIG_FOLDER"):
    CONFIG_FOLDER = Path(_dir)
else:
    CONFIG_FOLDER = Path(__file__).parent.parent.parent.with_name("data")
CONFIG_FOLDER.mkdir(exist_ok=True)


TELEGRAM_API_TOKEN: str = env("TELEGRAM_API_TOKEN", required=True)  # type: ignore

ADMINS: list[str] = env("ADMINS", required=True, is_list=True)  # type: ignore
CHAT_ID = int(env("CHAT_ID", required=True))  # type: ignore

SUFFIX = env("SUFFIX", "")

AUTO_START = env("AUTO_START", True)
SHOW_CHARACTER_TAG = env("SHOW_CHARACTER_TAG", True)
SHOW_ARTIST_TAG = env("SHOW_ARTIST_TAG", True)
SHOW_ID = env("SHOW_ID", True)
SHOW_BUTTONS = env("SHOW_BUTTONS", True)
DIRECT_BUTTON = env("DIRECT_BUTTON", False)
SHOW_DATE = env("SHOW_DATE", True)
NO_FILE = env("NO_FILE", False)
FORCE_FILE = env("FORCE_FILE", False)
EXPLICIT_FILE = env("EXPLICIT_FILE", False)
QUESTIONABLE_FILE = env("QUESTIONABLE_FILE", False)
DATE_FORMAT = env("DATE_FORMAT", "%b %-d '%y at %H:%M")  # Date like "Apr 4 '20 at 14:08"

# Delay before posts are sent after upload so that first corrections can take place
GRACE_PERIOD = int(env("GRACE_PERIOD", 0))  # type: ignore

SEARCH_TAGS = env("SEARCH_TAGS", "rating:safe")  # AND filter
POST_TAG_FILTER = env("POST_TAG_FILTER", set())  # OR filter
MAX_TAGS = int(env("MAX_TAGS", 15))  # type: ignore
SHOWN_TAGS = env(
    "SHOWN_TAGS",
    {  # Tags that will always be shown. Other tags will be selected randomly to reach MAX_TAGS
        "1girl",
        "2girls",
        "3girls",
        "4girls",
        "5girls",
        "6+girls",
        "highres",
        "blue_eyes",
        "blonde_hair",
        "yuri",
        "hololive",
        "animated",
    },
)

LAST_100_TRACK = env(
    "LAST_100_TRACK", False
)  # Track last 100 posts base on SEARCH_TAGS to recognize edited posts that newly match your criteria

# in min
RELOAD_INTEVAL = int(env("RELOAD_INTEVAL", 5))  # type: ignore

SERVICE = {
    "name": "danbooru",
    "url": "https://danbooru.donmai.us",
    "api": env("DANBOORU_API"),
    "username": env("DANBOORU_USERNAME"),
    "password": env("DANBOORU_PASSWORD"),
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
if env("WEBHOOK", True):
    host = env("WEBHOOK_HOST", required=True)
    port = int(env("WEBHOOK_PORT", 80))  # type: ignore
    path = env("WEBHOOK_PATH", "danbooru_channel_bot")
    listen = env("WEBHOOK_LISTEN", "0.0.0.0")  # type: ignore

    MODE: dict = {
        "active": "webhook",  # "webook" or "polling"
        "configuration": {
            "listen": listen,
            "port": port,
            "url_path": TELEGRAM_API_TOKEN,
            "webhook_url": f"https://{host}/{path}",
        },
    }

    print(f"{'*' * 50}\nWebhook listening to {MODE['configuration']['webhook_url']} on {listen}:{port}\n{'*' * 50}")  # type: ignore
else:
    MODE = {
        "active": "polling",
    }

if env("DEBUG", False):
    LOG_LEVEL = logging.DEBUG
else:
    LOG_LEVEL = logging.WARNING
