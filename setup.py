from setuptools import find_packages, setup

version = "1.1.2.dev0"

setup(
    name="DanbooruChannelBot",
    version=version,
    description="I post stuff uploaded to danbooru to a channel.",
    long_description=f'{open("README.rst").read()}\n{open("CHANGELOG.rst").read()}',
    author="Nachtalb",
    url="https://github.com/Nachtalb/DanbooruChannelBot",
    license="GPL3",
    packages=find_packages(exclude=["ez_setup"]),
    namespace_packages=["danbooru"],
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "emoji==2.2.0",
        "ffmpeg-python==0.2.0",
        "ffprobe-python==1.0.3",
        "Pybooru==4.2.2",
        "python-dotenv==0.21.1",
        "python-telegram-bot==13.15",
        "pyvips==2.2.1",
        "requests-html==0.10.0",
        "timeout-decorator==0.5.0",
        "yarl==1.8.2",
    ],
    extras_require={
        "dev": [
            "ipython[black]",
            "ipdb",
        ]
    },
    entry_points={
        "console_scripts": [
            "bot = danbooru.bot.bot:main",
        ]
    },
)
