from PIL import Image
from telegram import Update
from telegram.ext import ContextTypes

from danbooru import app
from danbooru.files.image import is_tg_compatible, make_tg_compatible
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

    for post in posts:
        caption = post_format(context.chat_data["config"], post)  # type: ignore
        await update.message.reply_text(post.best_file_url)
        if post.is_image:
            if problems := is_tg_compatible(post):
                with Image.open(await app.api.download(post.best_file_url)) as pil_image:
                    image = {"photo": make_tg_compatible(pil_image, problems), "filename": "image.jpeg"}
            else:
                image = {"photo": post.best_file_url}

            await update.message.reply_photo(caption=caption, **image)
        elif post.is_video or post.is_gif:
            await update.message.reply_video(post.best_file_url, caption=caption)
