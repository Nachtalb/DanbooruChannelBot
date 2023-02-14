from pydantic import BaseModel

from danbooru.models.post import Post, RATING


class SubscriptionGroup(BaseModel):
    name: str
    include: set[str] = set()
    exclude: set[str] = set()
    include_full_match: bool = False
    exclude_full_match: bool = False


class ChatConfig(BaseModel):
    show_direct_button: bool = True
    show_source_button: bool = True
    show_danbooru_button: bool = True
    template: str = (
        "Posted at: {posted_at}\nID: {id}\nTags: {tags}\nArtists: {artists}\nCharacters:"
        " {characters}\n\n@doIfis_channels"
    )
    send_as_files_threshold: str = ""
    subscription_groups: list[SubscriptionGroup] = []
    subscription_groups_or: bool = False  # False = OR, True = AND

    @property
    def send_as_files(self) -> bool:
        return self.send_as_files_threshold != ""

    def get_subscription_group(self, name: str) -> SubscriptionGroup | None:
        return next(filter(lambda group: group.name == name, self.subscription_groups), None)

    def post_allowed(self, post: Post) -> bool:
        if not self.subscription_groups:
            return True

        results = []
        for group in self.subscription_groups:
            tags = post.tags_with_rating

            include = tags & group.include == group.include if group.include_full_match else tags & group.include
            exclude = tags & group.exclude == group.exclude if group.exclude_full_match else tags & group.exclude

            results.append(include and not exclude)

        return any(results) if self.subscription_groups_or else all(results)

    def post_above_threshold(self, post: Post) -> bool:
        if not self.send_as_files or not post.rating:
            return False
        return RATING.level(post.rating) >= RATING.level(self.send_as_files_threshold)
