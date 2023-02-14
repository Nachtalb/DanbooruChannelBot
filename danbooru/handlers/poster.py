from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from yarl import URL

from danbooru import app
from danbooru.context import ChatData, CustomContext
from danbooru.files import document, image, video
from danbooru.models import Post
from danbooru.utils import post_format


async def post(update: Update, context: CustomContext) -> None:
    if context.args:
        try:
            arg_one = int(context.args[0])
            if len(context.args) > 1:
                posts = await app.api.posts(tags=context.args[1:], limit=arg_one)
            else:
                posts = [await app.api.post(int(context.args[0]))]
        except ValueError:
            posts = await app.api.posts(tags=context.args, limit=2)
    else:
        posts = await app.api.posts(2)

    await _send_posts(update, context, posts)


async def _send_posts(update: Update, context: CustomContext, posts: list[Post]):
    if not update.message:
        return

    for task, post in [(_prepare_file(context.chat_data, post), post) for post in posts]:  # type: ignore
        data = await task
        if not data:
            continue

        try:
            await _send_to_chat(update, context, data, post)
        except BadRequest:
            if isinstance(data.get("photo", data.get("video", data.get("document"))), str):
                new_data = await _prepare_file(context.chat_data, post, force_download=True)
                if new_data:
                    await _send_to_chat(update, context, new_data, post)
                    continue
            raise


async def _send_to_chat(update: Update, context: CustomContext, data: dict, post: Post):
    if not update.message:
        return

    if "text" in data:
        await update.message.reply_text(
            f"{data['text']}\n\n{post_format(context.chat_data, post)}",  # type: ignore
            reply_markup=_get_markup(context.chat_data, post),  # type: ignore
        )
        return

    data.update(
        {
            "caption": post_format(context.chat_data, post),  # type: ignore
            "reply_markup": _get_markup(context.chat_data, post),  # type: ignore
        }
    )

    #  await update.message.reply_text(data["filename"])
    if "photo" in data:
        await update.message.reply_photo(**data)
    elif "video" in data:
        await update.message.reply_video(**data)
    elif "document" in data:
        await update.message.reply_document(**data)


def _get_markup(chat: ChatData, post: Post):
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


async def _prepare_file(config: ChatData, post: Post, force_download: bool = False) -> dict | None:
    if post.is_bad or not config.post_allowed(post):
        return

    file = None

    if config.post_above_threshold(post):
        file, file_ext, as_document = await document.ensure_tg_compatibility(post, force_download)

    if not file and post.is_image:
        file, file_ext, as_document = await image.ensure_tg_compatibility(post, force_download)
        if file and not as_document:
            return {"photo": file, "filename": f"{post.id}.{file_ext}" if file_ext else post.filename}

    if not file and (post.is_video or post.is_gif):
        file, file_ext, as_document = await video.ensure_tg_compatibility(post, force_download)
        if file and not as_document:
            return {"video": file, "filename": f"{post.id}.{file_ext}" if file_ext else post.filename}

    if file:
        return {"document": file, "filename": post.filename}
    return {"text": "⚠️ The file is too big to be sent (limit on Telegrams side)"}
