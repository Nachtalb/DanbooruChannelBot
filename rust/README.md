# Danbooru Channel Bot (Rust)

Rust rewrite of the Python bot in the parent directory. Same `.env` settings (see `../README.rst`),
same files in `CONFIG_FOLDER` (`last_post.txt`, `tracker.txt`, `sub_config.json`), same commands.

```bash
cp ../.prod.env ../.env   # and fill it in
docker compose up -d --build
```

Without Docker you need `ffmpeg`/`ffprobe` on the `PATH` (for webm and ugoira conversion):

```bash
cargo run --release       # reads .env from the working directory
cargo test
```

## Differences to the Python version

- `/restart`, `/settings`, `/pdb` and `/ipdb` are gone (a binary can't reload itself; `/settings` was broken).
- `DANBOORU_PASSWORD` is unused, authentication is `DANBOORU_USERNAME` + `DANBOORU_API`.
- Ratings map to Danbooru's current names: `rating:general`, `rating:sensitive`, `rating:questionable`,
  `rating:explicit` (the old code tagged `g` posts as explicit).
- `CONFIG_FOLDER` defaults to `./data`.
- Config commands also work in channels, replies use HTML instead of Markdown.
