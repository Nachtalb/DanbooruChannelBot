from danbooru.bot.animedatabase_utils.base_service import BaseService
from pybooru import Danbooru as PyDanbooru
from pybooru.resources import SITE_LIST
from requests_html import HTMLSession

SITE_LIST['safebooru'] = {'url': 'https://safebooru.donmai.us'}


class DanbooruService(BaseService):
    FREE_LEVEL = 20
    GOLD_LEVEL = 30
    PLATINUM_LEVEL = 31
    BUILDER = 32
    JANITOR = 35
    MODERATOR = 40
    ADMIN = 50

    LEVEL_RESTRICTIONS = {
        'tag_limit': {
            FREE_LEVEL: 2,
            GOLD_LEVEL: 6,
            PLATINUM_LEVEL: 12,
            BUILDER: 32,
            JANITOR: 35,
            MODERATOR: 40,
            ADMIN: 50,
        },
        'censored_tags': {
            FREE_LEVEL: True,
            GOLD_LEVEL: False,
            PLATINUM_LEVEL: False,
            BUILDER: False,
            JANITOR: False,
            MODERATOR: False,
            ADMIN: False,
        }
    }

    type = 'danbooru'

    def __init__(self, name: str, url: str, api: str = None, username: str = None, password: str = None) -> None:
        super(DanbooruService, self).__init__(name=name, url=url, api=api, username=username, password=password)
        self.user_level = None
        self.session: HTMLSession

        self.init_client()
        self.init_session()

    def init_client(self):
        if self.api:
            if not self.username:
                raise ValueError('Danbooru API Services need a Username when API key is given.')
            self.client = PyDanbooru(site_name=self.name, site_url=self.url, api_key=self.api, username=self.username)
        else:
            self.client = PyDanbooru(site_name=self.name, site_url=self.url)

        self.user_level = self.get_user_level()
        self.tag_limit = self.LEVEL_RESTRICTIONS['tag_limit'][self.user_level]
        self.censored_tags = self.LEVEL_RESTRICTIONS['censored_tags'][self.user_level]

        if not self.url:
            self.url = self.client.site_url.lstrip('/')

    def init_session(self):
        self.session = HTMLSession()

    def get_user_level(self):
        user_level = 20
        if self.username:
            user = self.client.user_list(name_matches=self.client.username)
            user_level = user[0]['level']
        return user_level
