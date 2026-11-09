#!/usr/bin/env bash
# Отримати Mosquitto без прав адміністратора (Ubuntu/Debian):
# завантажує .deb-пакети і розпаковує їх у tools/mosq. Обгортки - у tools/bin.
# (Якщо є sudo, простіше: sudo apt install mosquitto mosquitto-clients)
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p debs mosq
(cd debs && apt-get download mosquitto mosquitto-clients libmosquitto1 libcjson1 \
   "$(apt-cache depends mosquitto | awk '/libwebsockets/{print $2; exit}')" libdlt2)
for d in debs/*.deb; do dpkg -x "$d" mosq; done
bin/mosquitto -h | head -1
