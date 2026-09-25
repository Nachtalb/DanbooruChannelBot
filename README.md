# Danbooru Channel Bot

Mirror [Danbooru](https://danbooru.donmai.us) posts, filtered or unfiltered, to a Telegram channel, group or
private chat. Other chats can subscribe to tags and get matching posts too. It runs
[@danbooru_dump](https://t.me/danbooru_dump), which mirrors all of Danbooru live.

## Running

Get a bot token from [@BotFather](https://t.me/BotFather), copy `.env.example` to `.env` and fill it in.

```bash
docker compose up -d --build
```

Without Docker you need Rust and `ffmpeg`/`ffprobe` on the `PATH`:

```bash
cargo run --release   # reads .env from the working directory
cargo test
```

## Settings

Set via environment variables or `.env` (which takes precedence and is reloaded by `/restart`).
Lists are comma separated, booleans are `1`, `true` or `yes`.

| Option | Default | Description |
|---|---|---|
| `TELEGRAM_API_TOKEN` | required | Bot token |
| `ADMINS` | | Telegram usernames allowed to control the bot |
| `CHAT_ID` | required | Main chat posts are sent to |
| `WEBHOOK` | `false` | Receive updates via webhook instead of polling |
| `WEBHOOK_HOST` | required with webhook | Public domain, Telegram posts to `https://WEBHOOK_HOST/WEBHOOK_PATH` |
| `WEBHOOK_PATH` | `danbooru_channel_bot` | Path the bot listens on |
| `WEBHOOK_PORT` / `WEBHOOK_LISTEN` | `5555` / `0.0.0.0` | Local address of the webhook server |
| `DANBOORU_USERNAME` / `DANBOORU_API` | | Danbooru login and API key (more search tags, restricted posts) |
| `LOG_LEVEL` | `info` | `off`, `error`, `warn`, `info`, `debug` or `trace` |
| `CONFIG_FOLDER` | `data` | Where runtime files are stored |
| `AUTO_START` | `true` | Start the refresh job on startup |
| `RELOAD_INTERVAL` | `5` | Minutes between refreshes |
| `GRACE_PERIOD` | `300` | Seconds a post must exist before it's sent, so first tag fixes land |
| `SEARCH_TAGS` | | Danbooru search (AND). Empty mirrors every new post |
| `POST_TAG_FILTER` | | Tags a post must have, `-tag` must not have |
| `LAST_100_TRACK` | `false` | With `SEARCH_TAGS`: remember the last 100 sent posts instead of the last id, so edited posts that newly match are sent |
| `MAX_TAGS` | `15` | Tags shown per post (artists and characters not counted) |
| `SHOWN_TAGS` | `1girl, …, animated` | Tags always shown if present, the rest is random |
| `SHOW_TAGS` / `SHOW_ARTIST_TAG` / `SHOW_CHARACTER_TAG` | `true` | Show general, artist, character tags |
| `SHOW_ID` / `SHOW_DATE` | `true` | Show post id / upload date |
| `DATE_FORMAT` | `%b %-d '%y at %H:%M` | [strftime](https://docs.rs/chrono/latest/chrono/format/strftime/) format, e.g. "Apr 4 '20 at 14:08" |
| `SHOW_BUTTONS` | `true` | Buttons linking the post and its source |
| `DIRECT_BUTTON` | `false` | Additional button linking the file |
| `NO_FILE` | `false` | Send text messages only |
| `FORCE_FILE` | `false` | Send everything as file (uncompressed) |
| `EXPLICIT_FILE` / `QUESTIONABLE_FILE` | `false` | Send explicit / questionable and explicit posts as file |
| `SUFFIX` | | HTML appended to each post, `{src}` and `{namedsrc}` insert the source link |

## Commands

Everyone:

- `/id` shows chat, message and user id.

Subscribers (in groups only group admins), configure which posts a chat gets and how they look:

- `/sub tag…` / `/unsub tag…` add or remove tags of the `OR` group: posts with any of them are sent.
- `/gsub group tag…` / `/gunsub group tag…` add or remove tags of a named group: posts with all of them are
  sent. `-tag` excludes posts in any group. `/gsub group` shows a group, `/gunsub group` deletes it.
  Tags may be written as hashtags, `rating:general`/`sensitive`/`questionable`/`explicit` works too.
- `/config [key [value]]` shows or sets `artist`, `buttons`, `characters`, `date_format`, `id`, `suffix`, `tags`,
  `time`, `no_file`, `direct_button`, `force_file`, `explicit_file`, `questionable_file` or `debug`
  (shows which group matched). `/<key> [value]` is a shortcut.

Bot admins:

- `/refresh` refresh now, `r` does the same and deletes the message.
- `/start` / `/stop` start or stop the refresh job, `/stop` also stops a manual refresh.
- `/cancel` cancels the running refresh.
- `/chat` shows the main chat.
- `/settings [KEY [value]]` shows or changes `LOG_LEVEL`, `SHOWN_TAGS`, `MAX_TAGS`, `SEARCH_TAGS`,
  `POST_TAG_FILTER`, `SHOW_ARTIST_TAG`, `SHOW_CHARACTER_TAG`, `CHAT_ID` or `ADMINS` until the next restart.
  Lists are replaced, `+a, b` adds and `-a` removes items.
- `/restart` restarts the bot, reloading `.env`.

## Copyright

Made by [Nachtalb](https://github.com/Nachtalb), licensed under the
[GNU General Public License v3.0](LICENSE).
