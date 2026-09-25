FROM rust:1-slim-bookworm AS build

WORKDIR /bot
COPY Cargo.toml Cargo.lock ./
COPY src src
RUN cargo build --release

FROM debian:bookworm-slim

RUN apt-get update && \
    apt-get install -yq --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/* && \
    useradd -u 1000 bot && \
    mkdir /config && chown bot /config

COPY --from=build /bot/target/release/danbooru-channel-bot /usr/local/bin/

USER bot
ENV CONFIG_FOLDER=/config
VOLUME /config
ENTRYPOINT ["danbooru-channel-bot"]
