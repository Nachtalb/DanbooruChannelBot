# syntax=docker/dockerfile:1
FROM rust:1.98-slim-trixie AS build

WORKDIR /bot
COPY . .
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/bot/target \
    cargo build --release --locked && \
    cp target/release/danbooru-channel-bot / && \
    mkdir /config

# Fully static ffmpeg/ffprobe (H.264, VP9, AV1, animated WebP/APNG) for video conversion
FROM mwader/static-ffmpeg:9.0.2 AS ffmpeg

FROM gcr.io/distroless/cc-debian13:nonroot

COPY --from=ffmpeg /ffmpeg /ffprobe /usr/local/bin/
COPY --from=build /danbooru-channel-bot /usr/local/bin/
COPY --from=build --chown=65532:65532 /config /config

ENV CONFIG_FOLDER=/config
VOLUME /config
# Graceful shutdown, so a post being sent isn't sent again after a restart
STOPSIGNAL SIGINT
ENTRYPOINT ["danbooru-channel-bot"]
