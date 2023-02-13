from io import BytesIO

from ..models import Post


async def ensure_tg_compatibility(post: Post) -> tuple[BytesIO | str, str | None, bool]:
    return post.best_file_url, None, False
