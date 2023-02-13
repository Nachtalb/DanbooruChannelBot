import re
from typing import Iterable

from .models import ChatConfig, Post


def post_format(config: ChatConfig, post: Post) -> str:
    return config.template.format(
        posted_at=post.created_at.strftime("%d/%m/%Y at %H:%M"),
        id=post.id,
        tags=", ".join(tg_tags(post.tags)),
        artists=", ".join(tg_tags(post.tags_artist)),
        characters=", ".join(tg_tags(post.tags_character)),
    )


def tg_tag(tag: str) -> str:
    return ("#" if not tag[0] == "#" else "") + re.sub(r"[\(\)\-:]", "_", tag).replace("__", "_").strip("_")


def tg_tags(tags: Iterable[str]) -> set[str]:
    return {tg_tag(tag) for tag in tags}
