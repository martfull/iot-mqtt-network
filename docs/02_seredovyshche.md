# Середовище для симуляції та програмування вбудованих систем

**Тема:** Мережа вузлів на MQTT з власним брокером
**Команда:** [ПІБ 1], [ПІБ 2], [ПІБ 3], [ПІБ 4]

---

## 1. Вибір симулятора

### 1.1. Порівняння симуляторів

Завдання: вивчити можливості симуляторів, обрати основний для команди й обґрунтувати вибір.

| Критерій | Wokwi | Cisco Packet Tracer | Tinkercad Circuits | PICSimLab | SimulIDE |
|---|---|---|---|---|---|
| Доступ | безкоштовно (публічні проєкти) | безкоштовно, реєстрація в Cisco NetAcad | безкоштовно, акаунт Autodesk | безкоштовно, відкритий код | безкоштовно, відкритий код |
| Де працює | браузер, VS Code, CLI | програма на ПК | браузер | програма на ПК, офлайн | програма на ПК |
| ESP32 | **так** | ні (умовні плати MCU-PT, SBC-PT) | ні (Arduino Uno) | уточнюється | ні (AVR, PIC) |
| Wi-Fi / вихід в Інтернет | **так** (віртуальна точка `Wokwi-GUEST`) | лише всередині моделі мережі | ні | ні | ні |
| MQTT | **так**, реальний брокер в Інтернеті | так, модельний брокер усередині PT | ні | обмежено | ні |
| Виконує реальну прошивку | **так** (той самий `.bin`, що й для плати) | ні (скрипти в стилі Arduino, JS, Python) | так (лише AVR) | так (HEX) | так (HEX) |
| Датчики | DHT22, BMP280, PIR, потенціометр тощо, з інтерактивною зміною значень | IoT-датчики PT | базові (TMP36…) | вбудовані в навчальні плати | аналогові компоненти, осцилограф |
| Git і автоматизація | `diagram.json` у Git, `wokwi-cli` + сценарії YAML | ні | ні | частково | частково |
| Обмеження | немає аналогового моделювання і вимірювання струму; приватні проєкти платні | не емулює ESP32, UART/SPI/I2C, FreeRTOS | немає мережі, ESP32, RTOS | мало компонентів і матеріалів | немає Wi-Fi і ESP32 |

### 1.2. Обґрунтування вибору: Wokwi

Тема 4 вимагає, щоб кілька пристроїв обмінювалися повідомленнями через MQTT-брокер. Звідси
три обов'язкові вимоги до симулятора: (1) мікроконтролер з Wi-Fi, (2) вихід у мережу до
реального брокера, (3) виконання тієї ж прошивки, що буде на платі. Усім трьом відповідає
**тільки Wokwi**. Це збігається з рекомендацією методички для тем 1–7, 11–13.

Додаткові переваги, які ми використали:
* `wokwi-cli` запускає симуляцію з командного рядка без браузера, а сценарій
  `scenario.yaml` автоматично змінює температуру DHT22 і перевіряє реакцію системи.
  Так «апаратний» тест стає відтворюваним;
* схема (`diagram.json`) і код зберігаються в Git разом з рештою проєкту;
* температуру й вологість DHT22 можна змінювати мишею під час симуляції, що зручно на захисті.

**Cisco Packet Tracer** розглядали як доповнення: він добре показує топологію (шлюз,
маршрутизатор, MQTT-брокер), але не виконує реальної прошивки ESP32. **Tinkercad,
PICSimLab, SimulIDE** не підходять, бо не мають мережі або MQTT.

### 1.3. Розподіл між симулятором і ПК

| Що | Де | Чому |
|---|---|---|
| Вузол ESP32 (DHT22 + вентилятор) | **Wokwi** | реальна прошивка мікроконтролера |
| Брокер (приватний) | Mosquitto на ПК | у Wokwi брокера немає; приватний брокер потрібен для дослідження QoS, ACL і TLS |
| Брокер (хмарний) | broker.hivemq.com | доступний і з Wokwi, і з ПК |
| Контролер, панель, логер | Python на ПК | у реальній системі це серверна частина, а не мікроконтролер |
| Додаткові вузли, навантажувальні тести | Python на ПК | десятки вузлів і тисячі повідомлень у Wokwi моделювати недоцільно |

Python-вузли використовують ті самі топіки й формат JSON, що й ESP32, тому для брокера і
контролера вони рівноправні.

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
| **Wokwi** (wokwi.com, `wokwi-cli` 0.29.1) | онлайн | **основний симулятор:** ESP32 DevKit + DHT22 + світлодіод |
| arduino-cli | 1.1.1 | компіляція прошивки ESP32 локально (для `wokwi-cli` і VS Code) |
| Ядро Arduino-ESP32 | 3.0.7 | платформа ESP32 (ESP-IDF 5.1) |
| PubSubClient / ArduinoJson / DHTesp | 2.8 / 7.2.1 / 1.19 | MQTT-клієнт, JSON, датчик DHT22 на ESP32 |
| VS Code / будь-який редактор | — | розробка |
| MQTT Explorer (за бажанням) | — | графічний перегляд дерева топіків |

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

### 3.3. Wokwi

**Варіант А — браузер (для демонстрації).** wokwi.com → New Project → ESP32 → вставити вміст
`wokwi/sketch/sketch.ino` і `diagram.json`, у Library Manager додати `PubSubClient`,
`ArduinoJson`, `DHT sensor library for ESPx` → Save → ▶. Проєкт команди:
[посилання на wokwi.com/projects/…].

**Варіант Б — командний рядок (для автоматичних тестів).**
```bash
# компілятор і ядро ESP32
arduino-cli config add board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core update-index && arduino-cli core install esp32:esp32@3.0.7
arduino-cli lib install PubSubClient@2.8 ArduinoJson@7.2.1 "DHT sensor library for ESPx@1.19"
arduino-cli compile --fqbn esp32:esp32:esp32 --output-dir wokwi/sketch/build wokwi/sketch

# симуляція (токен: wokwi.com/dashboard/ci; у Git не зберігається)
export WOKWI_CLI_TOKEN=...
ON=23 OFF=22 ./run_cloud.sh &                       # контролер на ПК через HiveMQ
wokwi-cli wokwi/sketch --scenario scenario.yaml --timeout 120000
```
`wokwi/sketch/wokwi.toml` вказує CLI і VS Code-розширенню на зібрані `build/sketch.ino.merged.bin`
та `.elf`.

### 3.4. Захищений режим (TLS + паролі)

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
├── wokwi/sketch/           # ESP32: sketch.ino, diagram.json, libraries.txt, wokwi.toml, scenario.yaml
├── tools/                  # локальний Mosquitto (bin/, get_mosquitto.sh)
├── results/                # результати вимірювань (CSV + MD)
├── docs/                   # звіти
├── run_demo.sh             # локальний контур (Mosquitto на ПК)
├── run_cloud.sh            # хмарний контур (HiveMQ, разом з ESP32 у Wokwi)
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

3. **wokwi-cli 0.15.1** (перша встановлена версія) не запустив симуляцію:
   `Error 2: File not found: test.elf`. Ця версія несумісна з поточним API симулятора. Після оновлення
   до 0.29.1 усе запрацювало.

4. **Публічні брокери.** TCP-порт 1883 усіх трьох брокерів був доступний, але
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
