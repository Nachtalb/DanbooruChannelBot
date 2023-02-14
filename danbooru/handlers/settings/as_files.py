from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from danbooru.models import ChatConfig
from danbooru.models.post import RATING
from danbooru.utils import set_emoji as se

from . import home


AS_FILES = 5


async def as_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message:
        return AS_FILES

    config: ChatConfig = context.chat_data["config"]  # type: ignore

    markup = ReplyKeyboardMarkup(
        [
            [
                f"All {se(config.send_as_files_threshold == RATING.g)}",
                f"Sensitive {se(config.send_as_files_threshold == RATING.s)}",
            ],
            [
                f"Questionable {se(config.send_as_files_threshold == RATING.q)}",
                f"Explicit {se(config.send_as_files_threshold == RATING.e)}",
            ],
            [
                f"Disable {se(config.send_as_files_threshold == '')}",
                f"Cancel",
            ],
        ],
        one_time_keyboard=True,
        selective=True,
    )

    await update.message.reply_text(
        "<b>SEND AS FILES</b>\n\nFrom which rating on should I send the art pieces as a file?", reply_markup=markup
    )
    return AS_FILES


async def change_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    config: ChatConfig = context.chat_data["config"]  # type: ignore
    match context.matches[0].groups()[0].lower():  # type: ignore
        case "all":
            config.send_as_files_threshold = RATING.general
        case "sensitive":
            config.send_as_files_threshold = RATING.sensitive
        case "questionable":
            config.send_as_files_threshold = RATING.questionable
        case "explicit":
            config.send_as_files_threshold = RATING.explicit
        case "disable":
            config.send_as_files_threshold = ""
    return await home(update, context)
