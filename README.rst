Danbooru Channel Bot
====================

.. image:: https://img.shields.io/badge/-Telegram-0088CC?logo=telegram&logoColor=white
   :target: https://t.me/angebote_des_tages_schweiz
   :alt: Danbooru Channel Bot Telegram

`GitHub <https://github.com/Nachtalb/DanbooruChannelBot>`__

Mirror Danbooru posts filtered or unflitered to any channel, group or private chat on
Telegram. It is used to run `@danbooru_dump <https://t.me/danbooru_dump>`__ which mirrors
the complete Danbooru live.

.. contents:: Table of Contents


Settings
--------

The settings are set via environmental variables. The bot supports ``.env`` files to make life easy. Just copy
``.prod.env`` to ``.env`` and fill in the data you want (optional settigns can be remvoed from the env file)

+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| Option             | Default                                                                                     | Definition                                                                         | Required                 | Type   |
+====================+=============================================================================================+====================================================================================+==========================+========+
| TELEGRAM_API_TOKEN | ``"XXX"``                                                                                   | Use @BotFather to get a token                                                      | yes                      | string |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| ADMINS             | ``"@User1, @User2"``                                                                        | Admins who control the bot                                                         | yes                      | list   |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| CHAT_ID            | ``100000000``                                                                               | Chat id to send posts to                                                           | yes                      | string |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| WEBHOOK_HOST       | ``"example.org"``                                                                           | Domain used for the webhook                                                        | yes if ``WEBHOOK=True``  | string |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| WEBHOOK_PATH       | ``"danbooru_channel_bot"``                                                                  | Path on the domain to identify this bot                                            | no                       | string |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| WEBHOOK_PORT       | ``5555``                                                                                    | Path the webhook is running on                                                     | no                       | int    |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| WEBHOOK            | ``True``                                                                                    | Use the webhook or pull updates from Telegram instead                              | yes                      | bool   |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| DANBOORU_API       | ``""``                                                                                      | API token for Danbooru                                                             | no                       | string |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| DANBOORU_USERNAME  | ``""``                                                                                      | Danbooru username                                                                  | no                       | string |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| DANBOORU_PASSWORD  | ``""``                                                                                      | Danbooru password                                                                  | no                       | string |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| DEBUG              | ``False``                                                                                   | Enable debug logging                                                               | no                       | bool   |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
|                    |                                                                                             |                                                                                    |                          |        |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| AUTO_START         | ``True``                                                                                    | Start the scheduler                                                                | no                       | bool   |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| SHOW_CHARACTER_TAG | ``True``                                                                                    | Show tags of all characters an the post                                            | no                       | bool   |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| SHOW_ARTIST_TAG    | ``True``                                                                                    | Show the artists tag                                                               | no                       | bool   |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| SHOW_ID            | ``True``                                                                                    | Show the posts id                                                                  | no                       | bool   |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| SEARCH_TAGS        | ``"rating:safe"``                                                                           | Search tags directly used on danbooru (AND filter)                                 | no                       | list   |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| POST_TAG_FILTER    | ``""``                                                                                      | Search tags evaluated by ourselves (OR filter)                                     | no                       | list   |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| MAX_TAGS           | ``10``                                                                                      | Max tags at once (general tags does not limit artist nor characters)               | no                       | int    |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| SHOWN_TAGS         | ``"1girl, 2girls, 3girls, 4girls, 5girls, 6+girls, highres, blue_eyes, blonde_hair, yuri"`` | Tags that will always be shown if available                                        | no                       | list   |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| SHOW_BUTTONS       | ``True``                                                                                    | Show link buttons to source                                                        | no                       | bool   |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| SHOW_DATE          | ``True``                                                                                    | Show post date                                                                     | no                       | bool   |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| DATE_FORMAT        | ``%b %-d '%y at %H:%M``                                                                     | Format of the shown date, default looks like: "Apr 4 '20 at 14:08"                 | no                       | string |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| LAST_100_TRACK     | ``False``                                                                                   | Track last 100 posts base on SEARCH_TAGS to recognize edited posts                 | no                       | bool   |
|                    |                                                                                             | that newly match your criteria                                                     |                          |        |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| SUFFIX             | ``""``                                                                                      | Suffix added to each post                                                          | no                       | string |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| RELOAD_INTEVAL     | ``5``                                                                                       | Danbooru reload interval in minutes                                                | no                       | int    |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+
| GRACE_PERIOD       | ``300``                                                                                     | Grace period before posing a new post from Danbooru (to prevent bad quality posts) | no                       | int    |
+--------------------+---------------------------------------------------------------------------------------------+------------------------------------------------------------------------------------+--------------------------+--------+


- ``string`` are just simple strings, nothing special here
- ``list`` a string with the list items separated by commas
- ``bool``  ``1``, ``true`` and ``yes`` are evaluate as ``True``, everything else is seen as ``False``
- ``int`` string which only consists of integers


Installation
------------

Get a Telegram Bot API Token > `@BotFather <https://t.me/BotFather>`__.

Copy the config ``.prod.env`` to ``.env`` and adjust it's values (see table above). It's
best to run in webhook mode, but if it's not possible just set it to ``False``.

The easies way to use it is to use it with Docker:

.. code:: bash

   docker compose build  # Build the image
   docker compose up     # Run the bot (use -d to run in the background)

To run it without Docker you can install the code with setuptools (preferably in a
virtualenv):

.. code:: bash

   python setup.py install

   # If you want to develop use `develop` instead of `install`
   # python setup.py develop

   # If you have pyenv you need to run this additionally:
   # pyenv rehash


To run the bot simply run

.. code:: bash

   bot


Copyright
---------

Thank you for using `@DanbooruChannelBot <https://t.me/DanbooruChannelBot>`__.

Made by `Nachtalb <https://github.com/Nachtalb>`_ | This extension licensed under the `GNU General Public License v3.0 <https://github.com/Nachtalb/DanbooruChannelBot/blob/master/LICENSE>`_.
