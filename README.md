# Мережа вузлів IoT на MQTT з власним брокером

https://wokwi.com/projects/480202739653048321

Командний мікропроєкт з дисципліни «Програмування вбудованих систем», **тема №4**.
Система має два контури:
* **локальний** — приватний брокер Mosquitto і програмні вузли на Python (`./run_demo.sh`);
* **хмарний** — вузол **ESP32 у симуляторі Wokwi** (DHT22 + вентилятор) працює через
  `broker.hivemq.com` разом з тим самим контролером, панеллю і логером на ПК (`./run_cloud.sh`).

## Склад

| Компонент | Файл | Роль у MQTT |
|---|---|---|
| Віртуальний датчик T/RH/P | `iotnet/sensor_node.py` | видавець (+ підписник на свої команди) |
| Віртуальний вентилятор (реле) | `iotnet/actuator_node.py` | підписник на команди, видавець стану |
| Контролер правил | `iotnet/controller.py` | підписник (wildcard) + видавець команд і тривог |
| Термінальна панель | `iotnet/dashboard.py` | підписник `iot/home/#` |
| Логер у SQLite | `iotnet/logger.py` | підписник з persistent session |
| Тест QoS | `experiments/qos_bench.py` | вимірювання доставки і затримки |
| Порівняння брокерів | `experiments/compare_brokers.py` | приватний брокер проти публічних |
| Конфіги брокера | `broker/` | Mosquitto dev/secure, ACL, TLS, amqtt |
| Вузол ESP32 (Wokwi) | `wokwi/sketch/` | прошивка C++, схема, сценарій автотесту |

## Швидкий старт

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
bash tools/get_mosquitto.sh        # Mosquitto без sudo (або: sudo apt install mosquitto mosquitto-clients)
./run_demo.sh                      # брокер + 2 датчики + 2 вентилятори + контролер + логер + панель
```

Ctrl+C зупиняє все. Логи процесів лежать у `logs/`, телеметрія в `data/telemetry.db`.

## ESP32 у Wokwi

**У браузері:** wokwi.com → New Project → ESP32 → вставити `wokwi/sketch/sketch.ino` і
`diagram.json`, у Library Manager додати `PubSubClient`, `ArduinoJson`,
`DHT sensor library for ESPx` → ▶. На ПК запустити `./run_cloud.sh`; клацнути по DHT22 і
підняти температуру вище 26 °C — засвітиться «FAN».

**З командного рядка** (потрібні `arduino-cli` з ядром `esp32:esp32@3.0.7` і токен Wokwi CI):
```bash
arduino-cli compile --fqbn esp32:esp32:esp32 --output-dir wokwi/sketch/build wokwi/sketch
ON=23 OFF=22 ./run_cloud.sh &
WOKWI_CLI_TOKEN=... wokwi-cli wokwi/sketch --scenario scenario.yaml --timeout 120000
```

## Експерименти

```bash
tools/bin/mosquitto -c broker/mosquitto-dev.conf &
.venv/bin/python -m experiments.compare_brokers            # локальний + публічні брокери
.venv/bin/python -m experiments.qos_bench -n 1000 --rate 0 # максимальна швидкість
```

Результати зберігаються в `results/*/compare.md` та `compare.csv`.

## Захищений режим (пароль + ACL + TLS)

```bash
PATH=$PWD/tools/bin:$PATH bash broker/setup_secure.sh
tools/bin/mosquitto -c broker/mosquitto-secure.conf -v
MQTT_PORT=8883 MQTT_TLS_CA=broker/secure/ca.crt MQTT_USER=t-kitchen MQTT_PASS=iot-demo-pass \
  .venv/bin/python -m iotnet.sensor_node --room kitchen --node t-kitchen
```

## Відомі особливості

* **amqtt** (`broker/amqtt.yaml`) залишено як запасний брокер на чистому Python. Під час
  тестів він (а) іноді надсилав retained-повідомлення з чужих топіків, (б) не зберігав
  QoS1/2-повідомлення для офлайн-клієнтів. Тому основний брокер — Mosquitto.
* PubSubClient на ESP32 публікує лише з QoS 0 (підписка — QoS 1).
* Wokwi-симуляція йде приблизно в 5 разів повільніше за реальний час, тому затримки міряємо на Python-вузлах.
* У Mosquitto 2.0.18 параметр `per_listener_settings true` вимикав черги для офлайн-клієнтів
  (перевірено), тому в конфігах його немає.

## Звіти

1. [Технічне завдання](docs/01_tekhnichne_zavdannia.md)
2. [Середовище для симуляції та програмування](docs/02_seredovyshche.md)
3. [Завдання для програмування](docs/03_zavdannia_prohramuvannia.md)
4. [Завдання для симуляції](docs/04_zavdannia_symuliatsii.md)
