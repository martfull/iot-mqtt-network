# Середовище для симуляції та програмування вбудованих систем

**Тема:** Мережа вузлів на MQTT з власним брокером
**Команда:** [ПІБ 1], [ПІБ 2], [ПІБ 3], [ПІБ 4]

---

## 1. Обґрунтування вибору

Мікроконтролерні вузли (на кшталт ESP32 з бібліотекою PubSubClient) у проєкті замінено
**програмною симуляцією на ПК**: кожен вузол — окремий процес Python зі своїм MQTT-клієнтом
і власним TCP-з'єднанням з брокером. Для брокера така модель нічим не відрізняється від
реальних пристроїв: він бачить незалежних клієнтів зі своїми client ID, сесіями, LWT і
keepalive. Тому досліджувати MQTT (QoS, retained, LWT, сесії, ACL, TLS) можна без заліза.
Логіка вузлів також легко переноситься на MicroPython (`umqtt`) або C++ (PubSubClient).

Переваги симуляції:
* можна запустити будь-яку кількість вузлів;
* аварійні ситуації відтворюються (`kill -9` замість вимкнення живлення, позаштатні сплески
  температури в моделі датчика);
* вимірювання затримки точні: видавець і підписник використовують один системний годинник.

## 2. Склад середовища

| Компонент | Версія | Призначення |
|---|---|---|
| ОС | Ubuntu 24.04 (Linux 6.17) | основна платформа |
| Python | 3.12 | мова реалізації вузлів і експериментів |
| paho-mqtt | 2.2.0 | MQTT-клієнт (API v2, MQTT 3.1.1) |
| Eclipse Mosquitto | 2.0.18 | приватний брокер; утиліти `mosquitto_pub`, `mosquitto_sub`, `mosquitto_passwd` |
| amqtt | 0.12.1 | запасний брокер на Python (див. п. 6) |
| SQLite 3 | вбудований у Python | журнал телеметрії |
| OpenSSL | 3.x | генерація CA і серверного сертифіката для TLS |
| VS Code / будь-який редактор | — | розробка |
| MQTT Explorer (за бажанням) | — | графічний перегляд дерева топіків |
| Wokwi (за бажанням) | онлайн | симулятор ESP32, якщо потрібен «апаратний» вузол |

Публічні хмарні брокери для порівняння: `test.mosquitto.org`, `broker.hivemq.com`,
`broker.emqx.io` (порт 1883, без автентифікації).

## 3. Встановлення

### 3.1. Python-оточення

```bash
cd iot-proj
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt      # paho-mqtt==2.2.0, amqtt==0.12.1
```

### 3.2. Брокер Mosquitto

З правами адміністратора:
```bash
sudo apt install mosquitto mosquitto-clients
sudo systemctl stop mosquitto      # системну службу вимикаємо, запускаємо зі своїм конфігом
```

Без прав адміністратора (так зроблено в проєкті): скрипт завантажує deb-пакети і
розпаковує їх у `tools/mosq/`, а обгортки в `tools/bin/` задають `LD_LIBRARY_PATH`:
```bash
bash tools/get_mosquitto.sh
tools/bin/mosquitto -h | head -1      # mosquitto version 2.0.18
```

### 3.3. Захищений режим (TLS + паролі)

```bash
PATH=$PWD/tools/bin:$PATH bash broker/setup_secure.sh
```
Скрипт створює `broker/secure/passwd` (користувачі `controller`, `dashboard`, `logger`,
`bench`, `t-kitchen`, `t-bedroom`, `fan-kitchen`, `fan-bedroom`), власний CA
(`ca.crt`) і серверний сертифікат для `localhost`/`127.0.0.1`.

## 4. Конфігурації брокера

| Файл | Режим | Особливості |
|---|---|---|
| `broker/mosquitto-dev.conf` | розробка | `127.0.0.1:1883`, анонімний доступ, persistence, `max_queued_messages 1000` |
| `broker/mosquitto-secure.conf` | захищений | анонімний доступ заборонено, паролі, ACL; `1883` лише localhost, `8883` з TLS 1.2+ |
| `broker/acl` | права | службові клієнти отримують ролі; вузли через `pattern ... %u` пишуть лише у свої топіки |
| `broker/amqtt.yaml` | запасний | брокер на Python, лише для розробки |

## 5. Структура проєкту

```
iot-proj/
├── iotnet/                 # програмні вузли
│   ├── config.py           # топіки, створення клієнта, env-змінні, TLS
│   ├── sensor_node.py      # датчик (видавець)
│   ├── actuator_node.py    # вентилятор (підписник)
│   ├── controller.py       # правила + тривоги
│   ├── dashboard.py        # термінальна панель
│   └── logger.py           # SQLite-журнал
├── experiments/
│   ├── qos_bench.py        # вимірювання QoS 0/1/2
│   └── compare_brokers.py  # приватний vs публічні
├── broker/                 # конфіги Mosquitto, ACL, TLS
├── tools/                  # локальний Mosquitto (bin/, get_mosquitto.sh)
├── results/                # результати вимірювань (CSV + MD)
├── docs/                   # звіти
├── run_demo.sh             # запуск усієї мережі
└── requirements.txt
```

## 6. Перевірка середовища і виявлені проблеми

Під час налаштування середовище перевірили так:

1. **Брокер amqtt.** Спершу брокером був amqtt (на чистому Python, не потребує
   встановлення). Тести виявили два дефекти:
   * вузли отримували retained-повідомлення `online` з **чужих** топіків статусу, на які
     не підписувалися (у журналі: `bad command on iot/home/kitchen/fan-kitchen/status`);
   * persistent session не зберігала QoS1/2-повідомлення для офлайн-клієнта
     (0 із 50 доставлено).

   Висновок: для досліджень потрібен еталонний брокер, тому обрано Mosquitto. У вузлах
   залишено захисну перевірку топіка (`if msg.topic != cmd_t: return`).

2. **Mosquitto і `per_listener_settings true`.** З цим параметром Mosquitto 2.0.18 так само
   не доставляв накопичені повідомлення офлайн-клієнту. Ізоляційний тест з утилітами
   `mosquitto_sub -c` / `mosquitto_pub`:

   | Конфіг | Отримано після повернення (3 повідомлення, QoS 1) |
   |---|---|
   | мінімальний | m1 m2 m3 |
   | + `per_listener_settings true` | — |
   | + `max_queued_messages 1000` | m1 m2 m3 |

   Параметр прибрано з обох конфігів.

3. **Публічні брокери.** TCP-порт 1883 усіх трьох брокерів був доступний, але
   `test.mosquitto.org` під час тестів (09.11.2026, двічі) не надіслав CONNACK за 10 с,
   тож він був перевантажений або обмежував клієнтів.

## 7. Запуск

```bash
./run_demo.sh
```
Скрипт перевіряє, чи зайнятий порт 1883. Якщо ні, запускає Mosquitto (або amqtt, коли
Mosquitto немає), а потім логер, контролер, 2 вентилятори, 2 датчики й панель. Вивід кожного
процесу пишеться в `logs/<name>.log`. Ctrl+C коректно зупиняє всі процеси.

Окремі вузли можна запускати вручну, наприклад:
```bash
.venv/bin/python -m iotnet.sensor_node --room lab --node t-lab --interval 1 --qos 1
tools/bin/mosquitto_sub -t 'iot/home/#' -v                    # «сирий» перегляд трафіку
tools/bin/mosquitto_pub -t iot/home/kitchen/fan-kitchen/cmd -m '{"power":"on"}'
```
