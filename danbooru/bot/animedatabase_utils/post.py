from datetime import datetime
from io import BytesIO
import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
from tempfile import TemporaryDirectory
from typing import Iterable
from zipfile import ZipFile

from requests.exceptions import ConnectionError

from danbooru.bot.animedatabase_utils.base_service import BaseService
import ffmpeg
import ffprobe


class Post:
    def __init__(self, post: dict, service: BaseService):
        self.post = post
        self.service = service
        self._file: BytesIO = None # type: ignore
        self._thumbnail = None
        self._fileext = None
        self.videos: Iterable
        self.audios: Iterable
        self._updated_at = None
        self._created_at = None
        self.logger = logging.getLogger(self.__class__.__name__)

    def __getattr__(self, item):
        return self.post[item]

    @property
    def updated_at(self) -> datetime:
        if not self._updated_at:
            self._updated_at = datetime.fromisoformat(self.post['updated_at'])
        return self._updated_at

    @property
    def created_at(self) -> datetime:
        if not self._created_at:
            self._created_at = datetime.fromisoformat(self.post['created_at'])
        return self._created_at

    @property
    def rating_tag(self) -> str:
        if self.rating == 's':
            return 'rating:safe'
        elif self.rating == 'q':
            return 'rating:questionable'
        return 'rating:explicit'

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
    def has_audio(self) -> bool:
        return bool(self.audio)

    @property
    def video(self) -> ffprobe.ffprobe.FFStream | None:
        self.prepare()
        return next(iter(self.videos), None)

    @property
    def audio(self) -> ffprobe.ffprobe.FFStream | None:
        self.prepare()
        return next(iter(self.audios), None)

    def prepare(self):
        self._download_file()

    def _get_video_probe(self) -> ffprobe.FFProbe:
        with NamedTemporaryFile(mode='bw') as file:
            file.write(self.file.read())
            self.file.seek(0)
            return ffprobe.FFProbe(file.name)

    def _set_file_info(self):
        probe = self._get_video_probe()
        self.videos = probe.video
        self.audios = probe.audio

    def _download_thumbnail(self) -> BytesIO | None:
        if self._thumbnail is None:
            try:
                self._thumbnail = BytesIO(self.service.session.get(self.post['preview_file_url']).content)
            except Exception as e:
                print(f'Error while downloading preview of {self.id}')
                print(e)

        return self._thumbnail

    def _download_file(self):
        if self._file is None:
            counter = 0
            while True:
                try:
                    self._file = BytesIO(self.service.session.get(self.file_url).content)
                    if self.file_extension == 'webm':
                        self._to_mp4()
                    if self.file_extension == 'zip':
                        self._zip_to_video()
                    break
                except ConnectionError as error:
                    counter += 1
                    if counter == 3:
                        raise error
        self._set_file_info()
        return self._file

    @property
    def thumbnail(self) -> BytesIO | None:
        if self._thumbnail is None:
            self._download_thumbnail()
        return self._thumbnail

    @property
    def file_url(self) -> str:
        if (self.post['file_url'].endswith('.zip') and
            (url := self.post.get('large_file_url', '')).endswith(('.mp4', '.webm')) and
            not self.post.get('pixiv_ugoira_frame_data', {}).get('data', [])):
            return url
        return self.post['file_url']

    @property
    def nice_file_url(self) -> str:
        if (self.post['file_url'].endswith('.zip') and
            (url := self.post.get('large_file_url', '')).endswith(('.mp4', '.webm'))):
            return url
        return self.post['file_url']

    @property
    def file(self) -> BytesIO:
        if self._file is None:
            self._download_file()
        return self._file  # type: ignore

    @property
    def file_extension(self) -> str | None:
        if self._fileext is None:
            self._fileext = Path(self.file_url).suffix.replace('.', '')
        return self._fileext

    def _get_delay(self) -> int:
        try:
            return self.pixiv_ugoira_frame_data['data'][0]['delay']
        except KeyError:
            return 66

    def _zip_to_video(self):
        with TemporaryDirectory() as tempdir:
            with ZipFile(self.file) as file:
                file.extractall(tempdir)

            image = next(Path(tempdir).glob('*'))
            self._to_mp4(tempdir + f'/*{image.suffix}', {
                'pattern_type': 'glob',
                'framerate': 1000 / self._get_delay(),
            })

    def _to_mp4(self, input: str | Path = 'pipe:', input_kwargs: dict[str, str | int | float] = {}):
        self.logger.info(f'[{self.id}] Converting from "{self.file_extension}" to "mp4"')
        self._file.seek(0)

        pipe_stdin = False
        if input == 'pipe:':
            pipe_stdin = True

        proc = (
            ffmpeg
            .input(input, **input_kwargs)
            .output('pipe:',
                    format='mp4',
                    movflags='frag_keyframe+empty_moov',
                    vf='pad=ceil(iw/2)*2:ceil(ih/2)*2')
            .global_args('-hide_banner')
            .run_async(pipe_stdin=pipe_stdin, pipe_stdout=True, pipe_stderr=True)
        )
        out, err = proc.communicate(input=self._file.read())

        if not out:
            self.logger.exception(err)
            return

        self._file = BytesIO()
        self._file.write(out)
        self._file.seek(0)

        self._fileext = 'mp4'
