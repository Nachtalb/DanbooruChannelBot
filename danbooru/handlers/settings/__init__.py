from asyncio import set_child_watcher
from io import BytesIO

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes, ConversationHandler

from danbooru.models.chat_config import ChatConfig
from danbooru.utils import bool_emoji as be

HOME = 1
WAIT_FOR_IMPORT = 19


async def home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return HOME

    config: ChatConfig = context.chat_data["config"]  # type: ignore

    markup = ReplyKeyboardMarkup(
        [
            [
                f"Toggle danbooru button {be(config.show_danbooru_button)}",
                f"Toggle source button {be(config.show_source_button)}",
            ],
            [f"Toggle direct button {be(config.show_direct_button)}", "Change message template"],
            ["Send posts as files", "Change tag filter"],
            ["Export", "Import"],
            ["Close"],
        ],
        one_time_keyboard=True,
        selective=True,
    )

    await update.message.reply_text(f"<b>SETTINGS</b>\n\nWhat do you want to change?\n", reply_markup=markup)
    return HOME


async def toggle_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    config: ChatConfig = context.chat_data["config"]  # type: ignore
    match context.matches[0].groups()[0].lower():  # type: ignore
        case "danbooru":
            config.show_danbooru_button = not config.show_danbooru_button
        case "direct":
            config.show_direct_button = not config.show_direct_button
        case "source":
            config.show_source_button = not config.show_source_button

    return await home(update, context)


async def cleanup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.chat_data:
        config = context.chat_data["config"]
        context.chat_data.clear()
        context.chat_data["config"] = config
    return ConversationHandler.END


async def full_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text(
            "Cancelled the current action", reply_markup=ReplyKeyboardRemove(selective=True)
        )
    return await cleanup(update, context)


async def export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return HOME
    config: ChatConfig = context.chat_data["config"]  # type: ignore

    file = BytesIO(config.json().encode())
    await update.message.reply_document(document=file, filename=f"{update.message.chat_id}.json")
    return await home(update, context)


async def wait_for_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return HOME

    await update.message.reply_text(
        "Send me the file you have previously exported. If it's from this chat it should be called"
        f" <code>{update.message.chat_id}.json</code>",
        reply_markup=ReplyKeyboardMarkup([["Cancel"]], one_time_keyboard=True, selective=True),
    )
    return WAIT_FOR_IMPORT


async def import_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.document:
        return WAIT_FOR_IMPORT

    tg_file = await update.message.document.get_file()
    if not tg_file.file_size or tg_file.file_size > 2000000:
        await update.message.reply_text("Have you uploaded the correct file?")
        return WAIT_FOR_IMPORT

    with BytesIO() as out:
        await tg_file.download_to_memory(out)
        try:
            config = ChatConfig.parse_raw(out.getvalue())
        except Exception:
            await update.message.reply_text("Have you uploaded the correct file?")
            return WAIT_FOR_IMPORT

    context.chat_data["config"] = config  # type: ignore
    await update.message.reply_text(f"{be(True)} Imported the settings successfully!")
    return await home(update, context)
