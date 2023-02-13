from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from yarl import URL

from danbooru import app
from danbooru.files import image, video
from danbooru.models import ChatConfig, Post
from danbooru.utils import post_format


async def post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    if context.args:
        try:
            arg_one = int(context.args[0])
            if len(context.args) > 1:
                posts = await app.api.posts(tags=context.args[1:], limit=arg_one)
            else:
                posts = [await app.api.post(int(context.args[0]))]
        except ValueError:
            posts = await app.api.posts(tags=context.args)
            print(f"search {context.args}, {len(posts)}")
    else:
        posts = await app.api.posts(2)

    config = context.chat_data["config"]  # type: ignore
    for index, (task, post) in enumerate([(_prepare_file(config, post), post) for post in posts]):
        print(f"{index}/{len(posts)} {post.id}")
        data = await task
        if not data:
            print(f"dropped {post.id}")
            continue

        data.update(
            {
                "caption": post_format(config, post),
                "reply_markup": _get_markup(config, post),
            }
        )

        await update.message.reply_text(data["filename"])
        if "photo" in data:
            await update.message.reply_photo(**data)
        elif "video" in data:
            await update.message.reply_video(**data)
        elif "document" in data:
            await update.message.reply_document(**data)


def _get_markup(chat: ChatConfig, post: Post):
    buttons = []
    if chat.show_danbooru_button:
        buttons.append(InlineKeyboardButton("📦", post.url))
    if chat.show_source_button and post.source and not post.source.startswith("file:"):
        match URL(post.source):
            case url if url.host in ["twitter.com", "t.co"]:
                emoji = "🐦"
            case url if url.host in ["pixiv.net"]:
                emoji = "🅿️"
            case _:
                emoji = "🌐"
        buttons.append(InlineKeyboardButton(emoji, post.source))
    if chat.show_direct_button:
        buttons.append(InlineKeyboardButton("🖼️", post.best_file_url))
    return InlineKeyboardMarkup([buttons])


async def _prepare_file(config: ChatConfig, post: Post) -> dict | None:
    if post.is_bad or not config.post_allowed(post):
        return

    file = None

    if post.is_image:
        file, file_ext, as_document = await image.ensure_tg_compatibility(post)
        if not as_document:
            return {"photo": file, "filename": f"{post.id}.{file_ext}" if file_ext else post.filename}

    if post.is_video or post.is_gif:
        file, file_ext, as_document = await video.ensure_tg_compatibility(post)
        if not as_document:
            return {"video": file, "filename": f"{post.id}.{file_ext}" if file_ext else post.filename}
    return {"document": file or await app.api.download(post.best_file_url), "filename": post.filename}
