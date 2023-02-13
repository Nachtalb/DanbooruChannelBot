import random
import re
from typing import Iterable, Sequence

from .models import ChatConfig, Post


def post_format(config: ChatConfig, post: Post) -> str:
    return config.template.format(
        posted_at=post.created_at.strftime("%d/%m/%Y at %H:%M"),
        id=post.id,
        tags=", ".join(sample(tg_tags(post.tags), 15)),
        artists=", ".join(tg_tags(post.tags_artist)),
        characters=", ".join(tg_tags(post.tags_character)),
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
