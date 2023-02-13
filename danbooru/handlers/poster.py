from asyncio import create_task, gather, to_thread

from PIL import Image
from telegram import Update
from telegram.ext import ContextTypes

from danbooru import app
from danbooru.files import image
from danbooru.models import ChatConfig, Post
from danbooru.utils import post_format


async def post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    if context.args:
        try:
            posts = [await app.api.post(int(context.args[0]))]
        except ValueError:
            await update.message.reply_text("First argument has to be an post id")
            return
    else:
        posts = await app.api.posts(2)

    for task in [_prepare_post(context.chat_data["config"], post) for post in posts]:  # type: ignore
        data = await task
        if not data:
            continue

        await update.message.reply_text(data["filename"])
        if "photo" in data:
            await update.message.reply_photo(**data)
        elif "video" in data:
            await update.message.reply_video(**data)
        elif "document" in data:
            await update.message.reply_document(**data)


async def _prepare_post(config: ChatConfig, post: Post) -> dict | None:
    if post.is_removed or not config.post_allowed(post):
        return

    caption = post_format(config, post)
    file = None

    if post.is_image:
        file, filename, as_document = await image.ensure_tg_compatibility(post)
        if not as_document:
            return {"photo": file, "filename": filename, "caption": caption}

    if post.is_video or post.is_gif:
        return {
            "video": post.best_file_url,
            "filename": post.filename,
            "caption": caption,
        }

    return {
        "document": file or await app.api.download(post.best_file_url),
        "caption": caption,
    }
