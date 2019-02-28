import os
from io import BytesIO

from requests.exceptions import ConnectionError

from danbooru.bot.animedatabase_utils.base_service import BaseService


class Post:
    def __init__(self, post: dict, service: BaseService):
        self.post = post
        self.service = service
        self._file = None

    def __getattr__(self, item):
        value = self.post.get(item)
        if value:
            return value
        raise AttributeError

    @property
    def link(self) -> str:
        return f'{self.service.url}/posts/{self.id}'

    @property
    def is_image(self) -> bool:
        return self.file_extension in ['jpg', 'jpeg', 'png']

    @property
    def is_video(self) -> bool:
        return self.file_extension in ['webm', 'mp4']

    @property
    def is_gif(self) -> bool:
        return self.file_extension in ['gif']

    @property
    def file(self) -> BytesIO:
        if not self._file:
            counter = 0
            while True:
                try:
                    self._file = BytesIO(self.service.session.get(self.post['file_url']).content)
                    break
                except ConnectionError as error:
                    counter += 1
                    if counter == 3:
                        raise error
        return self._file

    @property
    def file_extension(self) -> str or None:
        split = os.path.splitext(self.post['file_url'])
        if len(split) != 2:
            return
        return split[1].lstrip('.')
