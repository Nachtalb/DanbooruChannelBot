from pydantic import BaseModel

from danbooru.models.post import Post


class SubscriptionGroup(BaseModel):
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
    send_as_files: bool = False
    send_as_files_threshold: str = "sensitive"
    subscription_groups: list[SubscriptionGroup] = []
    subscription_groups_or: bool = False  # False = OR, True = AND

    def post_allowed(self, post: Post) -> bool:
        if not self.subscription_groups:
            return True

        results = []
        for group in self.subscription_groups:
            include = (
                post.tags & group.include == group.include if group.include_full_match else post.tags & group.include
            )
            exclude = (
                post.tags & group.exclude == group.exclude if group.exclude_full_match else post.tags & group.exclude
            )

            results.append(include and not exclude)

        return any(results) if self.subscription_groups_or else all(results)