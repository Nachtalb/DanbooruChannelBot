FROM python:3.8.4-buster

LABEL maintainer="Nachtalb"
ARG CACHEBUST=1

WORKDIR /bot
COPY docker/ /root/

RUN \
 echo "**** install packages ****" && \
 apt update && \
 apt install -yq \
   ffmpeg
RUN \
 echo "**** install app ****" && \
  curl -sSL "https://github.com/Nachtalb/DanbooruChannelBot/archive/docker.zip" -o /tmp/app.zip && \
  unzip /tmp/app.zip -d /bot && \
  mv /bot/DanbooruChannelBot-docker/* /bot && \
  rm -rf DanbooruChannelBot-docker && \
  pip uninstall setuptools -y && \
  ln -s production.cfg buildout.cfg && \
  python3 bootstrap.py && \
  bin/buildout && \
  cp danbooru/bot/settings.example.py danbooru/bot/settings.py
RUN \
 echo "**** cleanup ****" && \
 apt clean -y && \
 rm -rf \
   /tmp/* \
   /var/lib/apt/lists/* \
   /var/tmp/* \
   /root/.cache

CMD bin/bot
# EXPOSE 5000
