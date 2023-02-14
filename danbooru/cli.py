import re

from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    Defaults,
    MessageHandler,
    filters,
)

from danbooru import app
from danbooru.api import Api
from danbooru.context import BotData, ChatData, CustomContext, UserData
from danbooru.context.persistence import PydanticPersistence
from danbooru.handlers import help, post, start
from danbooru.handlers import settings
from danbooru.handlers.settings import as_files, subscription_groups as sg, template
from danbooru.handlers.settings.subscription_groups import (
    delete as sg_delete,
    edit as sg_edit,
    list as sg_list,
    new as sg_new,
)
from danbooru.models import Config

if __name__ == "__main__":
    app.config = Config()  # type: ignore

    context_types = ContextTypes(context=CustomContext, chat_data=ChatData, user_data=UserData, bot_data=BotData)
    persistence = PydanticPersistence(app.config.DATA_DIR)

    app.application = (
        ApplicationBuilder()
        .post_init(app.post_init)
        .post_shutdown(app.post_shutdown)
        .token(app.config.BOT_TOKEN)
        .defaults(Defaults(parse_mode=ParseMode.HTML))
        .context_types(context_types)
        .persistence(persistence)
        .build()
    )

    app.api = Api(user=app.config.DANBOORU_USERNAME, key=app.config.DANBOORU_KEY)

    app.application.add_handler(CommandHandler("start", start))
    app.application.add_handler(CommandHandler("help", help))
    app.application.add_handler(CommandHandler("post", post))

    TEXT_ONLY = filters.TEXT & (~filters.COMMAND)

    settings_conversation = {
        settings.HOME: [
            MessageHandler(filters.Regex(r"^Toggle (\w+) button"), settings.toggle_button),
            MessageHandler(filters.Regex(r"^Change message template$"), template.template),
            MessageHandler(filters.Regex(r"^Send posts as files$"), as_files.as_files),
            MessageHandler(filters.Regex(r"^Change tag filter$"), sg.subscription_groups),
            MessageHandler(filters.Regex(r"^Export$"), settings.export),
            MessageHandler(filters.Regex(r"^Import$"), settings.wait_for_import),
            MessageHandler(filters.Regex(r"^Close$"), settings.cleanup),
        ],
        settings.WAIT_FOR_IMPORT: [
            MessageHandler(filters.Document.ALL, settings.import_settings),
            MessageHandler(filters.Regex(r"^Cancel$"), settings.home),
        ],
        template.TEMPLATE: [
            MessageHandler(filters.Regex(r"^Save$"), template.save),
            MessageHandler(filters.Regex(r"^Send example post$"), template.send_example_post),
            MessageHandler(filters.Regex(r"^Reset$"), template.reset),
            MessageHandler(filters.Regex(r"^Cancel$"), template.cancel),
            MessageHandler(TEXT_ONLY, template.change_template),
        ],
        as_files.AS_FILES: [
            MessageHandler(filters.Regex(r"^(All|Sensitive|Questionable|Explicit|Disable)"), as_files.change_threshold),
            MessageHandler(filters.Regex(r"^Cancel$"), settings.home),
        ],
        sg.HOME_SUBSCRIPTION_GROUPS: [
            MessageHandler(filters.Regex(r"^Edit existing groups$"), sg_list.list_subscription_groups),
            MessageHandler(filters.Regex(r"^Create new group$"), sg_new.new_subscription_groups),
            MessageHandler(filters.Regex(r"^Delete a group$"), sg_delete.delete_subscription_groups),
            MessageHandler(filters.Regex(r"^Toggle group policy"), sg.group_policy),
            MessageHandler(filters.Regex(r"^Test groups$"), sg.test_group),
            MessageHandler(filters.Regex(r"^Back$"), settings.home),
        ],
        sg.TEST_SUBSCRIPTION_GROUPS: [
            MessageHandler(filters.Regex(r"^Cancel$"), sg.subscription_groups),
            MessageHandler(TEXT_ONLY, sg.run_test_group),
        ],
        sg_delete.DELETE_1_SUBSCRIPTION_GROUPS: [
            MessageHandler(filters.Regex(r"^Cancel$"), sg.subscription_groups),
            MessageHandler(TEXT_ONLY, sg_delete.confirmation),
        ],
        sg_delete.DELETE_2_SUBSCRIPTION_GROUPS: [
            MessageHandler(filters.Regex(r"^(Yes|No)$"), sg_delete.delete),
        ],
        sg_edit.EDIT_1_SUBSCRIPTION_GROUPS: [
            MessageHandler(filters.Regex(r"^(Include|Exclude)$"), sg_edit.edit_tags),
            MessageHandler(filters.Regex(r"^Toggle (include|exclude) full match"), sg_edit.toggle_full_match),
            MessageHandler(filters.Regex(r"^(Save|Cancel)$"), sg_edit.cancel),
            MessageHandler(TEXT_ONLY, sg_edit.edit_subscription_groups),
        ],
        sg_edit.EDIT_2_SUBSCRIPTION_GROUPS: [
            MessageHandler(filters.Regex(r"^Save$"), sg_edit.save_tags),
            MessageHandler(filters.Regex(r"^Cancel$"), sg_edit.cancel_tags),
            MessageHandler(TEXT_ONLY, sg_edit.set_tags),
        ],
    }

    settings_handler = ConversationHandler(
        name="settings",
        entry_points=[CommandHandler("settings", settings.home)],
        states=settings_conversation,
        fallbacks=[MessageHandler(filters.Regex(re.compile(r"^/?cancel$", re.IGNORECASE)), settings.full_cancel)],
        persistent=True,
    )

    app.application.add_handler(settings_handler)

    if not app.config.WEBHOOK:
        app.application.run_polling()
