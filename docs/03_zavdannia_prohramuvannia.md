# Завдання для програмування

**Тема:** Мережа вузлів на MQTT з власним брокером
**Команда:** [ПІБ 1], [ПІБ 2], [ПІБ 3], [ПІБ 4]

---

## 1. Постановка завдання

Розробити програмне забезпечення для мережі IoT-вузлів, які взаємодіють через власний
MQTT-брокер:
1. вузли-видавці (датчики мікроклімату);
2. вузли-підписники (виконавці — вентилятори);
3. контролер з правилами автоматизації і тривогами;
4. засоби моніторингу (панель) і збереження даних (логер);
5. конфігурацію брокера з автентифікацією, ACL і TLS;
6. інструменти для вимірювання характеристик доставки;
7. прошивку мікроконтролерного вузла ESP32 для симулятора Wokwi.

Мови: Python 3.12 (`paho-mqtt` 2.2, Callback API v2) — серверна частина і програмні вузли;
C++ (Arduino-ESP32 3.0.7) — прошивка ESP32.

## 2. Спільний модуль `iotnet/config.py`

Містить схему топіків і фабрику клієнтів. Параметри підключення беруться зі змінних середовища,
тому той самий код працює з локальним, захищеним або хмарним брокером:

| Змінна | За замовчуванням | Призначення |
|---|---|---|
| `MQTT_HOST` / `MQTT_PORT` | `127.0.0.1` / `1883` | адреса брокера |
| `MQTT_USER` / `MQTT_PASS` | — | автентифікація |
| `MQTT_TLS_CA` | — | шлях до `ca.crt`; якщо задано, вмикається TLS |
| `IOT_SITE` | `home` | другий рівень дерева топіків |

```python
def node_topic(room, node, kind, site=SITE):
    return f"{ROOT}/{site}/{room}/{node}/{kind}"     # iot/home/kitchen/t-kitchen/telemetry

def make_client(client_id=None, ..., clean_session=True):
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid, clean_session=clean_session)
    if u: c.username_pw_set(u, p)
    if MQTT_TLS_CA: c.tls_set(ca_certs=MQTT_TLS_CA)
    c.reconnect_delay_set(min_delay=1, max_delay=10)   # автоматичне перепідключення
```

## 3. Вузол-датчик `sensor_node.py`

### 3.1. Модель датчика

Клас `SimSensor` генерує правдоподібні показники:
* **температура** = базова + 3·sin(2πt/600) (добовий хід, стиснутий до 10 хв) + сплеск + шум N(0; 0,2);
* **позаштатна ситуація**: з імовірністю 2 % на кожному кроці виникає сплеск +6…10 °C, який
  затухає з коефіцієнтом 0,9 за крок (імітація перегріву);
* **вологість** змінюється в протифазі до температури (50 − 8·sin), обмежена діапазоном 0–100 %;
* **тиск** = 1013 + 2·sin(2πt/1800) + шум.

### 3.2. Логіка MQTT

```python
c.will_set(status_t, "offline", qos=1, retain=True)        # LWT - реєструється ДО connect

def on_connect(client, userdata, flags, rc, props=None):
    client.publish(status_t, "online", qos=1, retain=True)  # retained-статус
    client.subscribe(cmd_t, qos=1)                          # повторна підписка після reconnect

while running:
    payload = {"node": ..., "seq": seq, "ts": time.time(), **sensor.read()}
    c.publish(tele_t, json.dumps(payload), qos=args.qos)
    time.sleep(state["interval"])
```

* Підписка виконується в `on_connect`, тому після перепідключення вона відновлюється.
* Поле `seq` дає змогу виявити пропуски, а `ts` — виміряти затримку.
* Команда `{"interval": N}` змінює період публікації без перезапуску вузла.
* Під час коректного завершення (SIGINT/SIGTERM) вузол сам публікує `offline`, бо LWT
  спрацьовує лише при аварійному обриві.

## 4. Вузол-виконавець `actuator_node.py`

* Підключається з `clean_session=False`, тож команди QoS 1, надіслані поки вентилятор
  офлайн, брокер доставить після повернення.
* Перевіряє команду: JSON, наявність ключа `power`, значення `on`/`off`. Некоректна команда
  потрапляє в журнал і ігнорується.
* Публікує стан у `.../state` з `retain=True`, тож панель одразу після запуску бачить, чи
  ввімкнено вентилятор.
* Повторна однакова команда стан не змінює (ідемпотентність).

```python
def on_message(client, userdata, msg):
    if msg.topic != cmd_t:      # захисна перевірка (див. звіт «Середовище», п. 6)
        return
    try:
        cmd = json.loads(msg.payload); power = cmd["power"]
        if power not in ("on", "off"): raise ValueError(power)
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        print(f"invalid command on {msg.topic}: {msg.payload!r}"); return
    if power != state["power"]:
        state.update(power=power, changed=time.time(), reason=cmd.get("reason", ""))
        publish_state(client)
```

## 5. Контролер `controller.py`

Підписується через шаблони на `iot/home/+/+/telemetry` і `iot/home/+/+/status`. Так один
підписник обслуговує будь-яку кількість кімнат без зміни коду.

### 5.1. Автоматичне виявлення виконавців

Контролер підписаний на `iot/<site>/+/+/state`. Кожен вузол, що публікує retained-стан
(Python-вентилятор `fan-kitchen` чи ESP32 `esp32-lab`), реєструється як виконавець своєї
кімнати. Оскільки стан retained, контролер дізнається про всіх виконавців одразу після
підписки, навіть якщо запуститься пізніше за них. Якщо в кімнаті ще немає виконавців,
команда йде вузлу з типовою назвою `fan-<room>`.

```python
if kind == "state":
    actuators.setdefault(room, set()).add(node)
...
for fan in sorted(actuators.get(room) or {args.fan_prefix + room}):
    client.publish(config.node_topic(room, fan, "cmd"), json.dumps(cmd), qos=1)
```

### 5.2. Регулювання з гістерезисом

Щоб вентилятор не «торохтів» біля порога, є два пороги: `--on 26` і `--off 24`:

```python
on   = fan_on.get(room, False)
want = True if t > args.on else False if t < args.off else on   # між порогами стан не змінюємо
if want != on:
    client.publish(node_topic(room, "fan-" + room, "cmd"),
                   json.dumps({"power": "on" if want else "off", "reason": f"t={t:.1f}°C"}), qos=1)
```

Команда надсилається лише тоді, коли потрібний стан змінився. Це не завантажує мережу
дубльованими командами.

### 5.3. Тривоги (QoS 2)

* `critical` — температура вища за поріг увімкнення більш ніж на 5 °C;
* `warning` — вузол перейшов в `offline`. Retained-повідомлення, отримані під час підписки,
  ігноруються (`msg.retain`), щоб після перезапуску контролера не сипалися старі тривоги.

## 6. Прошивка ESP32 (`wokwi/sketch/sketch.ino`)

### 6.1. Апаратна частина (схема `diagram.json`)

| Компонент | Підключення | Призначення |
|---|---|---|
| ESP32 DevKit C v4 | — | мікроконтролер з Wi-Fi |
| DHT22 | VCC→3V3, GND→GND, SDA→**GPIO15** | температура і вологість |
| Світлодіод синій «FAN» + резистор 220 Ом | анод через резистор → **GPIO2**, катод → GND | імітація реле вентилятора |

### 6.2. Структура програми

```
setup(): Serial 115200 → GPIO → DHT22 → client ID з MAC → Wi-Fi (Wokwi-GUEST) → NTP → MQTT-сервер, callback, keepalive 10 с
loop():  Wi-Fi втрачено? → перепідключення
         MQTT не підключено? → спроба раз на 3 с (неблокуюче), return
         mqtt.loop() → обробка вхідних команд
         минуло intervalMs? → прочитати DHT22 → JSON → publish telemetry
```

Ключові фрагменти:

```cpp
// LWT передається в CONNECT: якщо ESP32 зникне, брокер сам опублікує "offline" (QoS1, retained)
bool ok = mqtt.connect(clientId, nullptr, nullptr, T_STATUS, 1, true, "offline");
mqtt.publish(T_STATUS, "online", true);   // retained
mqtt.subscribe(T_CMD, 1);
publishState();                           // retained-стан -> контролер знаходить виконавця

void onMessage(char *topic, byte *payload, unsigned int len) {
  if (strcmp(topic, T_CMD) != 0) return;            // захист від чужих повідомлень
  JsonDocument d;
  if (deserializeJson(d, payload, len)) { /* invalid JSON -> журнал */ return; }
  if (d["power"].is<const char *>()) { ... setFan(true/false, reason); }
  if (d["interval"].is<float>())     { intervalMs = max(0.5, s) * 1000; }
}
```

* Топіки збираються макросом на етапі компіляції:
  `#define TOPIC(kind) "iot/" IOT_SITE "/" IOT_ROOM "/" IOT_NODE "/" kind`.
* **Client ID** = `martfull-esp32-lab-<3 байти MAC>`, унікальний на публічному брокері.
  Якщо два клієнти мають однаковий ID, брокер відключає попереднього.
* **Час `ts`** береться з NTP (`configTime`). Поки час не синхронізовано, поле не
  надсилається. Значення серіалізується як `serialized(String(ts, 3))`, бо ArduinoJson
  інакше друкує double як `1.794217374e9` і губить мілісекунди. Цю помилку знайшли під час тестів.
* **Помилки DHT22** (`dht.getStatus() != ERROR_NONE`) потрапляють у журнал, а невдалий вимір
  не публікується.

### 6.3. Обмеження PubSubClient

Бібліотека PubSubClient публікує **лише з QoS 0**, а підписуватися вміє з QoS 0/1. Тому
телеметрія ESP32 має QoS 0, що відповідає рекомендації зі звіту «Симуляція»: для частої
телеметрії QoS 0 оптимальний. Команди контролер надсилає з QoS 1, і брокер доставляє їх
ESP32 з QoS 1, бо підписка зроблена з QoS 1. Якщо потрібна QoS 1/2-публікація з ESP32,
є альтернативи: `AsyncMqttClient` або вбудований клієнт ESP-IDF (`esp_mqtt_client`).

### 6.4. Ресурси

Скомпільовано `arduino-cli compile --fqbn esp32:esp32:esp32`:
**944 769 байт flash (72 %)**, **45 616 байт RAM (13 %)**. Основну частину займає стек Wi-Fi/TCP.

## 7. Панель `dashboard.py` і логер `logger.py`

**Панель** підписується на `iot/home/#` і раз на секунду перемальовує таблицю (ANSI-коди):
вузол, статус (зелений/червоний), T/RH/P, номер повідомлення, стан вентилятора і позначка
«нема даних N s», якщо телеметрія не надходила понад 10 с. Нижче показано 5 останніх тривог.

**Логер** використовує persistent session (`client_id="logger"`, `clean_session=False`) і
пише дані в SQLite:

```sql
CREATE TABLE telemetry(ts REAL, room TEXT, node TEXT, seq INTEGER,
                       temperature REAL, humidity REAL, pressure REAL, latency_ms REAL);
CREATE TABLE events(ts REAL, topic TEXT, payload TEXT);   -- статуси і тривоги
```

Поле `latency_ms` дорівнює часу отримання мінус `ts` з повідомлення, тобто це наскрізна
затримка датчик → брокер → логер.

## 8. Безпека брокера

ACL (`broker/acl`) реалізує принцип найменших привілеїв. Логін вузла збігається з його
ім'ям у топіку, тож правило з `%u` обмежує вузол лише його власною гілкою:

```
user controller
topic read  iot/home/+/+/telemetry
topic write iot/home/+/+/cmd
topic write iot/home/alerts

pattern write     iot/home/+/%u/telemetry     # t-kitchen пише ЛИШЕ в .../t-kitchen/telemetry
pattern read      iot/home/+/%u/cmd
```

Результати перевірки (Mosquitto 2.0.18, `mosquitto-secure.conf`):

| Перевірка | Результат |
|---|---|
| Анонімне підключення | `Connection Refused: not authorised` |
| Неправильний пароль | `Connection Refused: not authorised` |
| `t-kitchen` публікує свою телеметрію | доставлено підписнику `dashboard` |
| `t-bedroom` підробляє телеметрію `t-kitchen` | відкинуто ACL, підписник не отримав |
| `t-kitchen` надсилає команду `fan-kitchen` | відкинуто ACL |
| Публікація через TLS (порт 8883, `--cafile ca.crt`) | успішно |
| Python-вузол з `MQTT_TLS_CA`, порт 8883 | підключився, публікує |

У MQTT 3.1.1 брокер не повідомляє видавцю про відмову ACL: повідомлення просто
не пересилається. Тому підробку перевіряли на боці підписника.

## 9. Інструменти вимірювання

`experiments/qos_bench.py`:
* **онлайн-тест** — N повідомлень із заданою частотою. Кожне повідомлення містить
  12-байтний заголовок `struct("!Iq")` (номер + час у наносекундах) і доповнення до
  потрібного розміру. Рахуються отримані, втрачені, дублікати, порушення порядку, затримка
  (min/p50/p95/max) і швидкість публікації. Для QoS 1/2 тест чекає підтвердження
  (`wait_for_publish`);
* **офлайн-тест** — підписник створює persistent session і відключається, видавець надсилає
  50 повідомлень, підписник повертається з тим самим client ID. Рахується, скільки
  повідомлень брокер зберіг. Наприкінці сесію прибирають (підключення з `clean_session=True`).

Щоб на публічних брокерах не було перехресного трафіку, кожен тест використовує унікальний
топік `bench/<uuid>/q<qos>`.

`experiments/compare_brokers.py` запускає обидва тести для кожного брокера і QoS та
зберігає результати в `results/<dir>/compare.csv` і `compare.md`. Якщо брокер недоступний,
помилка потрапляє в таблицю і запуск не переривається.

## 10. Обробка помилок і надійність

| Ситуація | Реакція |
|---|---|
| Некоректний JSON або команда | журнал, ігнорування, вузол працює далі |
| Обрив з'єднання з брокером | автоматичне перепідключення (1–10 с), повторна підписка в `on_connect` |
| Аварійне завершення вузла | брокер публікує LWT `offline`, контролер піднімає тривогу |
| Коректне завершення | вузол сам публікує `offline` |
| Повідомлення з «чужого» топіка | ігнорується перевіркою `msg.topic` |
| Публічний брокер недоступний | `TimeoutError` записується в таблицю результатів |
| ESP32: втрата Wi-Fi / MQTT | повторне підключення Wi-Fi; MQTT — неблокуючі спроби раз на 3 с |
| ESP32: помилка DHT22 | журнал, вимір пропускається |
| Однаковий client ID на публічному брокері | префікс сайту (`martfull-…`) у всіх клієнтів, у ESP32 ще й MAC |
