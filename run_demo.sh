#!/usr/bin/env bash
# Запускає всю мережу: брокер + 2 датчики + 2 вентилятори + контролер + логер,
# і показує панель у цьому терміналі. Ctrl+C - зупинити все.
set -u
cd "$(dirname "$0")"
PY=.venv/bin/python
export PATH="$PWD/tools/bin:$PATH"   # локальний Mosquitto, якщо розпакований
mkdir -p logs data/mosquitto
PIDS=()
start() { local name=$1; shift; "$@" > "logs/$name.log" 2>&1 & PIDS+=($!); }
cleanup() { kill "${PIDS[@]}" 2>/dev/null; wait 2>/dev/null; echo "Зупинено."; }
trap cleanup EXIT INT TERM

if ! (exec 3<>/dev/tcp/127.0.0.1/1883) 2>/dev/null; then
  if command -v mosquitto >/dev/null; then
    echo "Запускаю Mosquitto..."; start broker mosquitto -c broker/mosquitto-dev.conf -v
  else
    echo "Mosquitto не знайдено - запускаю amqtt (Python)..."; start broker .venv/bin/amqtt -c broker/amqtt.yaml
  fi
  for _ in $(seq 30); do (exec 3<>/dev/tcp/127.0.0.1/1883) 2>/dev/null && break; sleep 0.2; done
else
  echo "Брокер на 127.0.0.1:1883 вже працює."
fi

start logger     $PY -m iotnet.logger
start controller $PY -m iotnet.controller --on 26 --off 24
start fan-kitchen $PY -m iotnet.actuator_node --room kitchen --node fan-kitchen
start fan-bedroom $PY -m iotnet.actuator_node --room bedroom --node fan-bedroom
start t-kitchen  $PY -m iotnet.sensor_node --room kitchen --node t-kitchen --base-temp 25 --qos 1
start t-bedroom  $PY -m iotnet.sensor_node --room bedroom --node t-bedroom --base-temp 21 --interval 3
sleep 1
$PY -m iotnet.dashboard
