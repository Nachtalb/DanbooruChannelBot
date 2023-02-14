import json
from pathlib import Path
from typing import Optional

from pydantic import ValidationError
from telegram.ext import DictPersistence, PersistenceInput

from danbooru.context.bot_data import BotData
from danbooru.context.chat_data import ChatData
from danbooru.context.user_data import UserData


class PydanticPersistence(DictPersistence):
    """Using pydantic's :obj:`pydantic.BaseModel` for making your bot persistent.

    Args:
        data_dir(:obj:`pathlib.Path`): Path to the stored data / where to save data
        store_data (:class:`~telegram.ext.PersistenceInput`, optional): Specifies which kinds of
            data will be saved by this persistence instance. By default, all available kinds of
            data will be saved.
        update_interval (:obj:`int` | :obj:`float`, optional): The
            :class:`~telegram.ext.Application` will update
            the persistence in regular intervals. This parameter specifies the time (in seconds) to
            wait between two consecutive runs of updating the persistence. Defaults to 60 seconds.

    Attributes:
        store_data (:class:`~telegram.ext.PersistenceInput`): Specifies which kinds of data will
            be saved by this persistence instance.
    """

    def __init__(
        self,
        data_directory: Path,
        store_data: PersistenceInput = None,  # type: ignore
        update_interval: float = 60,
    ):
        self._data_directory = data_directory

        user_data_json, chat_data_json, bot_data_json, callback_data_json, conversations_json = self._load_from_dir()

        super().__init__(
            store_data=store_data,
            callback_data_json=callback_data_json,
            conversations_json=conversations_json,
            update_interval=update_interval,
        )

        if user_data_json:
            try:
                self._user_data = self._decode_user_data_from_json(user_data_json)
                self._user_data_json = user_data_json
            except ValidationError as exc:
                raise TypeError("Unable to deserialize user_data_json.") from exc
        if chat_data_json:
            try:
                self._chat_data = self._decode_chat_data_from_json(chat_data_json)
                self._chat_data_json = chat_data_json
            except ValidationError as exc:
                raise TypeError("Unable to deserialize chat_data_json.") from exc
        if bot_data_json:
            try:
                self._bot_data = self._decode_bot_data_from_json(bot_data_json)
                self._bot_data_json = bot_data_json
            except ValidationError as exc:
                raise TypeError("Unable to deserialize bot_data_json.") from exc

    @property
    def user_data(self) -> Optional[dict[int, UserData]]:
        """:obj:`UserData`: the user_data as a pydantic instance."""
        return self._user_data

    @property
    def user_data_json(self) -> str:
        """:obj:`str`: the user_data serialized as a json-string."""
        if self._user_data_json:
            return self._user_data_json
        # FIXME json.loads(data.json()) is to ensure we don't get errors like "datetime is
        # not json serializable" but it's not very efficient. It works for now... (famous last words)
        return (
            json.dumps({uid: json.loads(data.json()) for uid, data in self.user_data.items()})
            if self.user_data
            else "{}"
        )

    @property
    def chat_data(self) -> Optional[dict[int, ChatData]]:
        """:obj:`ChatData`: the chat_data as a pydantic instance."""
        return self._chat_data

    @property
    def chat_data_json(self) -> str:
        """:obj:`str`: the chat_data serialized as a json-string."""
        if self._chat_data_json:
            return self._chat_data_json
        # FIXME json.loads(data.json()) is to ensure we don't get errors like "datetime is
        # not json serializable" but it's not very efficient. It works for now... (famous last words)
        return (
            json.dumps({cid: json.loads(data.json()) for cid, data in self.chat_data.items()})
            if self.chat_data
            else "{}"
        )

    @property
    def bot_data(self) -> Optional[BotData]:
        """:obj:`BotData`: the bot_data as a pydantic instance."""
        return self._bot_data

    @property
    def bot_data_json(self) -> str:
        """:obj:`str`: the bot_data serialized as a json-string."""
        if self._bot_data_json:
            return self._bot_data_json
        return self.bot_data.json() if self.bot_data else ""

    async def get_user_data(self) -> dict[int, UserData]:
        """Returns the user_data created from the ``user_data_json`` or an empty :obj:`dict`.

        Returns:
            :obj:`dict`: The restored user data.
        """

        if self.user_data is None:
            self._user_data = {}
        return {uid: data.copy(deep=True) for uid, data in self.user_data.items()} if self.user_data else {}

    async def get_chat_data(self) -> dict[int, ChatData]:
        """Returns the chat_data created from the ``chat_data_json`` or an empty :obj:`dict`.

        Returns:
            :obj:`dict`: The restored chat data.
        """
        if self.chat_data is None:
            self._chat_data = {}
        return {cid: data.copy(deep=True) for cid, data in self.chat_data.items()} if self.chat_data else {}

    async def get_bot_data(self) -> BotData:
        """Returns the bot_data created from the ``bot_data_json`` or an empty :obj:`BotData`.

        Returns:
            :obj:`BotData`: The restored bot data.
        """
        if self.bot_data is None:
            self._bot_data = BotData()
        return self.bot_data.copy(deep=True)  # type: ignore[attr]

    async def update_user_data(self, user_id: int, data: UserData) -> None:
        """Will update the user_data (if changed).

        Args:
            user_id (:obj:`int`): The user the data might have been changed for.
            data (:obj:`dict`): The :attr:`telegram.ext.Application.user_data` ``[user_id]``.
        """
        if self._user_data is None:
            self._user_data = {}
        if self._user_data.get(user_id) == data:
            return
        self._user_data[user_id] = data
        self._user_data_json = None

    async def update_chat_data(self, chat_id: int, data: ChatData) -> None:
        """Will update the chat_data (if changed).

        Args:
            chat_id (:obj:`int`): The chat the data might have been changed for.
            data (:obj:`dict`): The :attr:`telegram.ext.Application.chat_data` ``[chat_id]``.
        """
        if self._chat_data is None:
            self._chat_data = {}
        if self._chat_data.get(chat_id) == data:
            return
        self._chat_data[chat_id] = data
        self._chat_data_json = None

    async def update_bot_data(self, data: BotData) -> None:
        """Will update the bot_data (if changed).

        Args:
            data (:obj:`dict`): The :attr:`telegram.ext.Application.bot_data`.
        """
        if self._bot_data == data:
            return
        self._bot_data = data
        self._bot_data_json = None

    def _load_from_dir(self) -> tuple[str, str, str, str, str]:
        """Will load all data from data directory"""
        return (
            file.read_text() if (file := self._data_directory / "user.json").is_file() else "",
            file.read_text() if (file := self._data_directory / "chat.json").is_file() else "",
            file.read_text() if (file := self._data_directory / "bot.json").is_file() else "",
            file.read_text() if (file := self._data_directory / "callback.json").is_file() else "",
            file.read_text() if (file := self._data_directory / "conversations.json").is_file() else "",
        )

    async def flush(self) -> None:
        """Will save all data in memory to json file(s)."""
        if self.user_data:
            (self._data_directory / "user.json").write_text(self.user_data_json)
        if self.chat_data:
            (self._data_directory / "chat.json").write_text(self.chat_data_json)
        if self.bot_data:
            (self._data_directory / "bot.json").write_text(self.bot_data_json)
        if self.callback_data:
            (self._data_directory / "callback.json").write_text(self.callback_data_json)
        if self.conversations:
            (self._data_directory / "conversations.json").write_text(self.conversations_json)

    @staticmethod
    def _decode_user_data_from_json(data: str) -> dict[int, UserData]:
        return {user_id: UserData.parse_obj(user_data) for user_id, user_data in json.loads(data).items()}

    @staticmethod
    def _decode_chat_data_from_json(data: str) -> dict[int, ChatData]:
        return {chat_id: ChatData.parse_obj(chat_data) for chat_id, chat_data in json.loads(data).items()}

    @staticmethod
    def _decode_bot_data_from_json(data: str) -> BotData:
        return BotData.parse_raw(data)
