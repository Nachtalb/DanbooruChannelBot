from io import BytesIO

from PIL import Image

from .. import app
from ..models import Post

IMAGE_RES_TOO_HIGH = 0
IMAGE_RATIO_TOO_HIGH = 1
IMAGE_SIZE_TOO_HIGH = 2

MAX_FILESIZE = 10000000  # 10 MB if we upload
TG_MAX_FILESIZE = 5000000  # 5 MB if we send url


def is_tg_compatible(post: Post) -> list[int]:
    result = []
    if post.image_width + post.image_height > 10000:
        # Max combined width and height of 10000
        result.append(IMAGE_RES_TOO_HIGH)

    if post.image_width / post.image_height <= 0.05 or post.image_height / post.image_width <= 0.05:
        # Max ratio of 1:20
        result.append(IMAGE_RATIO_TOO_HIGH)

    if post.file_size > TG_MAX_FILESIZE:
        # Max size of 20MB
        result.append(IMAGE_SIZE_TOO_HIGH)

    return result


def decrease_image_size(image: Image.Image, out: BytesIO, max_size: int = MAX_FILESIZE) -> BytesIO:
    image.save(out, format="jpeg")

    while out.getbuffer().nbytes >= max_size:
        image = image.resize((int(image.width * 0.9), int(image.height * 0.9)))
        out.seek(0)
        out.truncate(0)
        image.save(out, format="jpeg")

    image.close()
    out.seek(0)
    return out


def make_tg_compatible(image: Image.Image, problems: list[int]) -> BytesIO:
    """Make image Telegram compatible

    - max 10MB -> decrease width/height
    - max resolution 10000px width or height -> decrease width/height
    - max ration of 1:20 -> send as document

    @returns tuple[Image, bool]: New image and if it should be sent as a file
    """
    if image.mode == "RGBA":
        white_background = Image.new("RGB", image.size, (255, 255, 255))
        white_background.paste(image, (0, 0), image)
        image = white_background

    if IMAGE_RES_TOO_HIGH in problems:
        ratio = 10000 / (image.width + image.height)
        image = image.resize((int(image.width * ratio), int(image.height * ratio)))

    return decrease_image_size(image, BytesIO())


def make_tg_document_compatible(image: Image.Image, problems: list[int]) -> BytesIO:
    """Make image Telegram compatible

    - max 10MB -> decrease width/height

    @returns tuple[Image, bool]: New image and if it should be sent as a file
    """
    bytes = BytesIO()
    image.save(bytes, format="jpeg")

    if IMAGE_SIZE_TOO_HIGH in problems:
        while bytes.getbuffer().nbytes >= MAX_FILESIZE:
            image = image.resize((int(image.width * 0.9), int(image.height * 0.9)))
            bytes.seek(0)
            bytes.truncate(0)
            image.save(bytes, format="jpeg")

    image.close()
    bytes.seek(0)
    return bytes


async def ensure_tg_compatibility(post: Post) -> tuple[BytesIO | str, str | None, bool]:
    if problems := is_tg_compatible(post):
        with Image.open(await app.api.download(post.best_file_url)) as pil_image:
            if IMAGE_RATIO_TOO_HIGH in problems:
                return decrease_image_size(pil_image, BytesIO()), None, True
            return make_tg_compatible(pil_image, problems), "jpg", False
    else:
        return post.best_file_url, None, False
