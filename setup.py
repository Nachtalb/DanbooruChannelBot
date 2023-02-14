from setuptools import find_packages, setup

version = "2.0.0.dev0"

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
        "aiohttp[speedups]=<3.0",
        "aiopath=<0.7",
        "emoji=<2.3",
        "Pillow=<9.5",
        "pydantic[dotenv]=<1.11",
        "python-telegram-bot[rate-limiter]=<21",
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
