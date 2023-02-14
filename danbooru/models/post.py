from datetime import datetime

from pydantic import BaseModel


class RATING:
    g = general = "rating:general"
    s = sensitive = "rating:sensitive"
    q = questionable = "rating:questionable"
    e = explicit = "rating:explicit"

    levels = {"rating:general": 0, "rating:sensitive": 1, "rating:questionable": 2, "rating:explicit": 3}

    @staticmethod
    def level(rating: str) -> int:
        return RATING.levels.get(getattr(RATING, rating, rating), 0)

    @staticmethod
    def simple(rating: str) -> str:
        return getattr(RATING, rating, rating).split(":")[-1]


class Post(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    uploader_id: int
    approver_id: int | None
    tag_string: str
    tag_string_general: str
    tag_string_artist: str
    tag_string_copyright: str
    tag_string_character: str
    tag_string_meta: str
    rating: str | None
    parent_id: int | None
    pixiv_id: int | None
    source: str
    md5: str | None
    file_url: str
    large_file_url: str | None
    preview_file_url: str | None
    file_ext: str
    file_size: int
    image_width: int
    image_height: int
    score: int
    up_score: int
    down_score: int
    fav_count: int
    tag_count_general: int
    tag_count_artist: int
    tag_count_copyright: int
    tag_count_character: int
    tag_count_meta: int
    last_comment_bumped_at: datetime | None
    last_noted_at: datetime | None
    has_large: bool
    has_children: bool
    has_visible_children: bool
    has_active_children: bool
    is_banned: bool
    is_deleted: bool
    is_flagged: bool
    is_pending: bool
    bit_flags: int

    @property
    def tags_rating(self) -> set[str]:
        return set([getattr(RATING, self.rating)]) if self.rating else set()

    @property
    def tags(self) -> set[str]:
        return set(self.tag_string.split())

    @property
    def tags_with_rating(self) -> set[str]:
        return self.tags & self.tags_rating

    @property
    def tags_general(self) -> set[str]:
        return set(self.tag_string_general.split())

    @property
    def tags_artist(self) -> set[str]:
        return set(self.tag_string_artist.split())

    @property
    def tags_copyright(self) -> set[str]:
        return set(self.tag_string_copyright.split())

    @property
    def tags_character(self) -> set[str]:
        return set(self.tag_string_character.split())

    @property
    def tags_meta(self) -> set[str]:
        return set(self.tag_string_meta.split())

    @property
    def url(self) -> str:
        return f"https://danbooru.donmai.us/posts/{self.id}"

    @property
    def is_image(self) -> bool:
        return self.file_ext in ["jpg", "jpeg", "png", "webp"]

    @property
    def is_gif(self) -> bool:
        return self.file_ext == "gif"

    @property
    def is_video(self) -> bool:
        return self.file_ext in ["mp4", "webm", "mkv"]

    @property
    def best_file_url(self) -> str:
        return self.file_url if not self.file_url.endswith("zip") else (self.large_file_url or self.file_url)

    @property
    def is_bad(self) -> bool:
        return self.is_banned or (self.is_deleted and ((self.up_score or 1) / abs(self.down_score or 1) < 2))

    @property
    def filename(self) -> str:
        return f"{self.id}.{self.file_ext}"
