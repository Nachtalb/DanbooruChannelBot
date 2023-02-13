from aiohttp import BasicAuth, ClientSession

from .models import Post


class Api:
    def __init__(self, user: str, key: str):
        self.session = ClientSession(base_url="https://danbooru.donmai.us/", auth=BasicAuth(user, key))
        self.user = user
        self.key = key

    async def posts(self) -> list[Post]:
        async with self.session.get("posts.json") as response:
            return [Post.parse_obj(item) for item in await response.json()]

    async def post(self, id: int) -> Post:
        async with self.session.get(f"posts/{id}.json") as response:
            return Post.parse_obj(await response.json())
