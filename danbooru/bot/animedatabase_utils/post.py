import os
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import cv2
import ffprobe
from requests.exceptions import ConnectionError

from danbooru.bot.animedatabase_utils.base_service import BaseService


class Post:
    def __init__(self, post: dict, service: BaseService):
        self.post = post
        self.service = service
        self._file = None
        self._thumbnail = None
        self._fileext = None
        self.videos = None
        self.audios = None

    def __getattr__(self, item):
        value = self.post.get(item)
        if value:
            return value
        raise KeyError

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
    def video(self) -> ffprobe.ffprobe.FFStream:
        self.prepare()
        return next(iter(self.videos), None)

    @property
    def audio(self) -> ffprobe.ffprobe.FFStream:
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

    def _download_thumbnail(self) -> BytesIO:
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
                    self._file = BytesIO(self.service.session.get(self.post['file_url']).content)
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
    def thumbnail(self) -> BytesIO:
        if self._thumbnail is None:
            self._download_thumbnail()
        return self._thumbnail

    @property
    def file(self) -> BytesIO:
        if self._file is None:
            self._download_file()
        return self._file

    @property
    def file_extension(self) -> str or none:
        if self._fileext is None:
            self._fileext = Path(self.file_url).suffix.replace('.', '')
        return self._fileext

    def _get_delay(self):
        try:
            return self.pixiv_ugoira_frame_data['data'][0]['delay']
        except KeyError:
            return 50

    def _extract_zip(self, zip_file, output_dir):
        with ZipFile(zip_file) as zip_file:
            zip_file.extractall(output_dir)

    def _generate_mp4_from_frames(self, output_file, frames_dir, delay):
        frames = sorted(map(lambda file: os.path.join(str(frames_dir), file), os.listdir(frames_dir)))
        frames = list(map(cv2.imread, frames))

        framerate = 1000 / delay

        height, width, layers = frames[0].shape
        video = cv2.VideoWriter(str(output_file), cv2.VideoWriter_fourcc(*'mp4v'), framerate, (width, height))

        for frame in frames:
            video.write(frame)

        cv2.destroyAllWindows()
        video.release()

    def _zip_to_video(self):
        with TemporaryDirectory() as dir:
            temp_dir = Path(dir)
            frames_dir = temp_dir / 'frames'
            self._extract_zip(self.file, frames_dir)

            video_file = temp_dir / 'out.mp4'
            self._generate_mp4_from_frames(video_file, frames_dir, self._get_delay())

            self._file = BytesIO()
            self._file.write(video_file.read_bytes())
            self._file.seek(0)
            self._fileext = 'mp4'
