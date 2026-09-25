FROM rust:1-slim-bookworm AS build

WORKDIR /bot
COPY Cargo.toml Cargo.lock ./
COPY src src
RUN cargo build --release

FROM debian:bookworm-slim

LABEL maintainer="Nachtalb"

RUN apt-get update && \
    apt-get install -yq --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/* && \
    useradd -u 1000 bot

COPY --from=build /bot/target/release/danbooru-channel-bot /usr/local/bin/

USER bot
ENV CONFIG_FOLDER=/config
ENTRYPOINT ["danbooru-channel-bot"]
