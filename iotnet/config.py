"""Спільні налаштування та схема топіків.

Структура топіків (MQTT topic tree):

    iot/<site>/<room>/<node>/telemetry   JSON з вимірами        QoS 0/1, не retained
    iot/<site>/<room>/<node>/status      "online"/"offline"     QoS 1, retained, LWT
    iot/<site>/<room>/<node>/cmd         JSON-команда до вузла  QoS 1 (або 2)
    iot/<site>/<room>/<node>/state       JSON-стан виконавця    QoS 1, retained
    iot/<site>/alerts                    JSON-тривоги           QoS 2

Підписка з wildcard-символами:
    iot/<site>/+/+/telemetry   - уся телеметрія сайту
    iot/<site>/#               - усе дерево сайту
"""
import os
import uuid

import paho.mqtt.client as mqtt

BROKER_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASS = os.getenv("MQTT_PASS")
MQTT_TLS_CA = os.getenv("MQTT_TLS_CA")  # шлях до ca.crt -> вмикає TLS
SITE = os.getenv("IOT_SITE", "home")
ROOT = "iot"


def node_topic(room: str, node: str, kind: str, site: str = SITE) -> str:
    return f"{ROOT}/{site}/{room}/{node}/{kind}"


def alerts_topic(site: str = SITE) -> str:
    return f"{ROOT}/{site}/alerts"


def parse_node_topic(topic: str):
    """'iot/home/kitchen/t1/telemetry' -> ('home','kitchen','t1','telemetry')"""
    parts = topic.split("/")
    if len(parts) == 5 and parts[0] == ROOT:
        return parts[1], parts[2], parts[3], parts[4]
    return None


def make_client(client_id: str | None = None, host: str | None = None,
                port: int | None = None, user: str | None = None,
                password: str | None = None, clean_session: bool = True) -> mqtt.Client:
    """Створює клієнта paho-mqtt (API v2) з облікові даними з env за потреби."""
    cid = client_id or f"iot-{uuid.uuid4().hex[:8]}"
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid,
                    clean_session=clean_session)
    u = user if user is not None else MQTT_USER
    p = password if password is not None else MQTT_PASS
    if u:
        c.username_pw_set(u, p)
    if MQTT_TLS_CA:
        c.tls_set(ca_certs=MQTT_TLS_CA)
    c.reconnect_delay_set(min_delay=1, max_delay=10)
    c._iot_host = host or BROKER_HOST  # noqa: SLF001 - зберігаємо для connect()
    c._iot_port = port or BROKER_PORT  # noqa: SLF001
    return c


def connect(c: mqtt.Client, keepalive: int = 10) -> None:
    c.connect(c._iot_host, c._iot_port, keepalive=keepalive)  # noqa: SLF001
