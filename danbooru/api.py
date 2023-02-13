from aiohttp import BasicAuth, ClientSession

from .models import Post


class Api:
    def __init__(self, session: ClientSession, user: str, key: str):
        self.session = session
        self._auth = BasicAuth(user, key)
        self.user = user
        self.key = key

    async def _request(self, endpoint: str, params: dict = {}) -> dict:
        async with self.session.get(
            f"https://danbooru.donmai.us/{endpoint}.json", params=params, auth=self._auth
        ) as response:
            return await response.json()

    async def posts(self) -> list[Post]:
        return [Post.parse_obj(item) for item in await self._request("posts")]

    async def post(self, id: int) -> Post:
        return Post.parse_obj(await self._request(f"posts/{id}"))
