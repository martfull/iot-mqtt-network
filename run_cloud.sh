#!/usr/bin/env bash
# Хмарний режим: контролер + логер (+ за бажанням Python-датчик) + панель підключаються
# до публічного брокера, де працює і вузол ESP32 у Wokwi (wokwi/sketch).
#   ./run_cloud.sh            - лише служби (вузол - ESP32 у Wokwi)
#   ./run_cloud.sh --with-py  - ще й Python-датчик + вентилятор у кімнаті "office"
# Пороги контролера можна змінити: ON=23 OFF=22 ./run_cloud.sh
set -u
cd "$(dirname "$0")"
PY=.venv/bin/python
export MQTT_HOST="${MQTT_HOST:-broker.hivemq.com}" MQTT_PORT="${MQTT_PORT:-1883}"
export IOT_SITE="${IOT_SITE:-martfull}"      # має збігатися з IOT_SITE у sketch.ino
mkdir -p logs data
PIDS=()
start() { local name=$1; shift; "$@" > "logs/cloud-$name.log" 2>&1 & PIDS+=($!); }
cleanup() { kill "${PIDS[@]}" 2>/dev/null; wait 2>/dev/null; echo "Зупинено."; }
trap cleanup EXIT INT TERM

echo "Брокер: $MQTT_HOST:$MQTT_PORT  топіки: iot/$IOT_SITE/#"
start logger     $PY -m iotnet.logger --db data/cloud.db
start controller $PY -m iotnet.controller --on "${ON:-26}" --off "${OFF:-24}"
if [ "${1:-}" = "--with-py" ]; then
  start fan-office $PY -m iotnet.actuator_node --room office --node fan-office
  start t-office   $PY -m iotnet.sensor_node --room office --node t-office --base-temp 25
fi
sleep 1
$PY -m iotnet.dashboard
