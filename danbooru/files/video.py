from io import BytesIO

from .. import app
from ..models import Post


TG_MAX_FILESIZE = 20000000  # 20 MB if we send url
MAX_FILESIZE = 50000000  # 50 MB if we send url


async def ensure_tg_compatibility(post: Post) -> tuple[BytesIO | str | None, str | None, bool]:
    if post.file_size > MAX_FILESIZE:
        return None, None, False
    elif post.file_size > TG_MAX_FILESIZE:
        return (await app.api.download(post.best_file_url)), None, False  # type: ignore
    return post.best_file_url, None, False
