from io import BytesIO

from danbooru import app
from danbooru.models import Post


TG_MAX_FILESIZE = 20000000  # 20 MB if we send url
MAX_FILESIZE = 50000000  # 50 MB if we send url


async def ensure_tg_compatibility(
    post: Post, force_download: bool = False
) -> tuple[BytesIO | str | None, str | None, bool]:
    if not force_download and post.file_size > MAX_FILESIZE:
        return None, None, True
    elif force_download or post.file_size > TG_MAX_FILESIZE:
        return (await app.api.download(post.best_file_url)), None, True  # type: ignore
    return post.best_file_url, None, True
