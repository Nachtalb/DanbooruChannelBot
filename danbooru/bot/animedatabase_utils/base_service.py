from requests_html import HTMLSession


class BaseService:
    type = 'base'

    def __init__(self, name: str, url: str, api: str = None, username: str = None, password: str = None):
        self.name = name
        self.url = url.lstrip('/') if url is not None else None
        self.api = api
        self.username = username
        self.password = password

        self.count_qualifiers_as_tag = False
        self.client = None
        self.session: HTMLSession
        self.tag_limit: int
        self.censored_tags: list[str]

    def init_client(self):
        raise NotImplemented

    def init_session(self):
        raise NotImplemented
