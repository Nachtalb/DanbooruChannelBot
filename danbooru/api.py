from io import BytesIO
from pathlib import Path

from aiohttp import BasicAuth, ClientSession
from aiopath import AsyncPath
from yarl import URL

from .models import Post


class Api:
    def __init__(self, user: str, key: str):
        self.session = ClientSession(auth=BasicAuth(user, key))
        self._base_url = URL("https://danbooru.donmai.us/")
        self.user = user
        self.key = key

    async def close(self):
        await self.session.close()

    async def posts(self, limit: int = 10, tags: list[str] = []) -> list[Post]:
        async with self.session.get(
            self._base_url / "posts.json", params={"limit": limit, "tags": " ".join(tags)}
        ) as response:
            return [Post.parse_obj(item) for item in await response.json()]

    async def post(self, id: int) -> Post:
        async with self.session.get(self._base_url / f"posts/{id}.json") as response:
            return Post.parse_obj(await response.json())

    async def download(self, url: str, out: Path | None = None) -> Path | BytesIO:
        async with self.session.get(url) as response:
            if out:
                aio_path = AsyncPath(out)
                await aio_path.write_bytes(await response.content.read())
                return out
            return BytesIO(await response.content.read())
