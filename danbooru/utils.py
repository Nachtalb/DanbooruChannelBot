import random
import re
from typing import Iterable, Sequence

from danbooru.models import ChatConfig, Post
from danbooru.models.post import RATING


def post_format(config: ChatConfig, post: Post) -> str:
    return config.template.format(
        posted_at=post.created_at.strftime("%d/%m/%Y at %H:%M"),
        id=post.id,
        tags=", ".join(sample(tg_tags(post.tags_general), 15)),
        artists=tg_tags_string(post.tags_artist),
        characters=tg_tags_string(post.tags_character),
        copyright=tg_tags_string(post.tags_character),
        meta=tg_tags_string(post.tags_character),
        rating="#" + (RATING.simple(post.rating) if post.rating else "unset"),
    )


def sample(population: Sequence, k: int) -> Sequence:
    return random.sample(population, k=len(population) if len(population) < k else k)


def tg_tag(tag: str) -> str | None:
    tag = re.sub("_{2,}", "", re.sub(r"\W", "_", tag)).strip("_")
    if tag:
        return ("#" if not tag[0] == "#" else "") + tag
    return


def tg_tags(tags: Iterable[str]) -> Sequence[str]:
    return tuple(filter(None, map(tg_tag, tags)))


def tg_tags_string(tags: Iterable[str]) -> str:
    return ", ".join(tg_tags(tags))


def bool_emoji(value: bool) -> str:
    return "🟢" if value else "🔴"


def set_emoji(value: bool) -> str:
    return "🟢" if value else ""


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]
