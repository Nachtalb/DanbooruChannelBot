from setuptools import find_packages, setup

version = '1.0.1.dev0'

setup(name='DanbooruChannelBot',
      version=version,
      description="I post stuff uploaded to danbooru to a channel.",
      long_description=f'{open("README.rst").read()}\n{open("CHANGELOG.rst").read()}',

      author='Nachtalb',
      url='https://github.com/Nachtalb/DanbooruChannelBot',
      license='GPL3',

      packages=find_packages(exclude=['ez_setup']),
      namespace_packages=['danbooru'],
      include_package_data=True,
      zip_safe=False,

      install_requires=[
          'mr.developer',
          'python-telegram-bot',
          'pybooru',
          'requests_html',
      ],

      entry_points={
          'console_scripts': [
              'bot = danbooru.bot.bot:main',
          ]
      })
