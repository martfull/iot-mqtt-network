/*
 * Вузол ESP32 для мережі IoT на MQTT (тема №4) - симулятор Wokwi.
 *
 * Апаратура (diagram.json): ESP32 DevKit v1, DHT22 (GPIO15), світлодіод-«вентилятор» (GPIO2).
 * Мережа: віртуальний Wi-Fi Wokwi-GUEST -> Інтернет -> хмарний брокер MQTT.
 *
 * Топіки (сумісні з Python-вузлами з iotnet/):
 *   iot/<site>/<room>/<node>/telemetry  JSON {node,room,seq,ts,temperature,humidity,rssi}
 *   iot/<site>/<room>/<node>/status     "online" / "offline" (retained, LWT)
 *   iot/<site>/<room>/<node>/state      JSON {power,changed,reason} (retained)
 *   iot/<site>/<room>/<node>/cmd        {"power":"on"|"off"} або {"interval":N}
 */
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <DHTesp.h>
#include <time.h>

// ---------- налаштування ----------
#define WIFI_SSID   "Wokwi-GUEST"
#define WIFI_PASS   ""
#define MQTT_HOST   "broker.hivemq.com"
#define MQTT_PORT   1883
#define IOT_SITE    "martfull"          // унікальний префікс на публічному брокері
#define IOT_ROOM    "lab"
#define IOT_NODE    "esp32-lab"
#define PIN_DHT     15
#define PIN_FAN     2
// -----------------------------------

#define TOPIC(kind) "iot/" IOT_SITE "/" IOT_ROOM "/" IOT_NODE "/" kind
const char *T_TELE   = TOPIC("telemetry");
const char *T_STATUS = TOPIC("status");
const char *T_STATE  = TOPIC("state");
const char *T_CMD    = TOPIC("cmd");

WiFiClient net;
PubSubClient mqtt(net);
DHTesp dht;

uint32_t seq = 0;
uint32_t intervalMs = 2000;
uint32_t lastPub = 0, lastTry = 0;
bool fanOn = false;
String fanReason = "boot";
time_t fanChanged = 0;
char clientId[32];

double nowEpoch() {                       // час з NTP (секунди з мс), 0 якщо ще не синхронізовано
  struct timeval tv;
  gettimeofday(&tv, nullptr);
  return tv.tv_sec > 1700000000 ? tv.tv_sec + tv.tv_usec / 1e6 : 0;
}

void publishState() {
  JsonDocument d;
  d["power"] = fanOn ? "on" : "off";
  d["changed"] = (double)fanChanged;
  d["reason"] = fanReason;
  char buf[160];
  size_t n = serializeJson(d, buf);
  mqtt.publish(T_STATE, (const uint8_t *)buf, n, true);    // retained
}

void setFan(bool on, const char *reason) {
  if (on == fanOn) return;                 // ідемпотентність: повтор команди нічого не змінює
  fanOn = on;
  fanReason = reason;
  fanChanged = (time_t)nowEpoch();
  digitalWrite(PIN_FAN, on ? HIGH : LOW);
  Serial.printf("[fan] power -> %s (%s)\n", on ? "on" : "off", reason);
  publishState();
}

void onMessage(char *topic, byte *payload, unsigned int len) {
  if (strcmp(topic, T_CMD) != 0) return;   // захист від чужих повідомлень
  JsonDocument d;
  if (deserializeJson(d, payload, len)) {
    Serial.printf("[cmd] invalid JSON: %.*s\n", len, (char *)payload);
    return;
  }
  if (d["power"].is<const char *>()) {
    const char *p = d["power"];
    const char *why = d["reason"] | "";
    if (!strcmp(p, "on")) setFan(true, why);
    else if (!strcmp(p, "off")) setFan(false, why);
    else Serial.printf("[cmd] unknown power value: %s\n", p);
  }
  if (d["interval"].is<float>()) {
    float s = d["interval"];
    intervalMs = (uint32_t)(max(0.5f, s) * 1000);
    Serial.printf("[cmd] interval -> %u ms\n", intervalMs);
  }
}

void connectWiFi() {
  Serial.printf("[wifi] connecting to %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS, 6);     // канал 6 - швидше підключення у Wokwi
  while (WiFi.status() != WL_CONNECTED) { delay(250); Serial.print('.'); }
  Serial.printf(" ok, IP=%s\n", WiFi.localIP().toString().c_str());
  configTime(0, 0, "pool.ntp.org");        // для поля ts у телеметрії
}

bool connectMqtt() {
  Serial.printf("[mqtt] connecting to %s:%d as %s ... ", MQTT_HOST, MQTT_PORT, clientId);
  // LWT: якщо ESP32 зникне без DISCONNECT, брокер сам опублікує "offline" (QoS1, retained)
  bool ok = mqtt.connect(clientId, nullptr, nullptr, T_STATUS, 1, true, "offline");
  if (!ok) { Serial.printf("fail, state=%d\n", mqtt.state()); return false; }
  Serial.println("ok");
  mqtt.publish(T_STATUS, "online", true);
  mqtt.subscribe(T_CMD, 1);
  publishState();
  return true;
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_FAN, OUTPUT);
  digitalWrite(PIN_FAN, LOW);
  dht.setup(PIN_DHT, DHTesp::DHT22);
  snprintf(clientId, sizeof clientId, "%s-%s-%06llx", IOT_SITE, IOT_NODE,
           ESP.getEfuseMac() & 0xFFFFFF);
  connectWiFi();
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);
  mqtt.setKeepAlive(10);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  if (!mqtt.connected()) {
    if (millis() - lastTry > 3000) {       // неблокуюче перепідключення раз на 3 с
      lastTry = millis();
      connectMqtt();
    }
    return;
  }
  mqtt.loop();

  if (millis() - lastPub >= intervalMs) {
    lastPub = millis();
    TempAndHumidity th = dht.getTempAndHumidity();
    if (dht.getStatus() != DHTesp::ERROR_NONE) {
      Serial.printf("[dht] error: %s\n", dht.getStatusString());
      return;
    }
    JsonDocument d;
    d["node"] = IOT_NODE;
    d["room"] = IOT_ROOM;
    d["seq"] = ++seq;
    double ts = nowEpoch();
    // serialized(): ArduinoJson інакше друкує double як 1.794217374e9 і губить мілісекунди
    if (ts > 0) d["ts"] = serialized(String(ts, 3));
    d["temperature"] = round(th.temperature * 100) / 100.0;
    d["humidity"] = round(th.humidity * 10) / 10.0;
    d["rssi"] = WiFi.RSSI();
    char buf[200];
    size_t n = serializeJson(d, buf);
    mqtt.publish(T_TELE, (const uint8_t *)buf, n, false);   // PubSubClient: публікація лише QoS 0
    Serial.printf("[tele] %s\n", buf);
  }
}
