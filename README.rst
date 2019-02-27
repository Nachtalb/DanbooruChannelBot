Danbooru Channel Bot
====================

`@DanbooruChannelBot <https://t.me/DanbooruChannelBot>`__ \|
`GitHub <https://github.com/Nachtalb/DanbooruChannelBot>`__

.. contents:: Table of Contents


What I do
---------

I post stuff uploaded to danbooru to a channel.


Development
-----------

For the project I chose `buildout <http://www.buildout.org/en/latest/contents.html>`__ instead of the default pip way.
I manly did this because it makes installation easier. I recommend to be in an virtualenv for any project, but this is
up to you. Now for the installation:

.. code:: bash

   ln -s development.cfg buildout.cfg
   python bootstrap.py
   bin/buildout

And everything should be installed. Now you can copy and configure your settings.

.. code:: bash

   cp danbooru/bot/settings.example.py  danbooru/bot/settings.py


Get a Telegram Bot API Token > `@BotFather <https://t.me/BotFather>`__ and put it inside your ``settings.py``.

To run the bot simply run

.. code:: bash

   bin/bot


Copyright
---------

Thank you for using `@DanbooruChannelBot <https://t.me/DanbooruChannelBot>`__.

Made by `Nachtalb <https://github.com/Nachtalb>`_ | This extension licensed under the `GNU General Public License v3.0 <https://github.com/Nachtalb/DanbooruChannelBot/blob/master/LICENSE>`_.
