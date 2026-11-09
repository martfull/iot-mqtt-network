"""Контролер (підписник + видавець): правила автоматизації.

Слухає телеметрію всіх кімнат (wildcard iot/<site>/+/+/telemetry) і статуси
вузлів. Правила:
  * temperature > ON_T  -> вентилятор кімнати ON;  < OFF_T -> OFF (гістерезис);
  * вузол перейшов у "offline" (LWT) -> тривога в iot/<site>/alerts (QoS 2).

Приклад:  python -m iotnet.controller --on 26 --off 24
"""
import argparse
import json
import signal
import time

from . import config


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--on", type=float, default=26.0, help="поріг увімкнення, °C")
    ap.add_argument("--off", type=float, default=24.0, help="поріг вимкнення, °C")
    ap.add_argument("--fan-prefix", default="fan-",
                    help="вентилятор кімнати = <prefix><room>, напр. fan-kitchen")
    args = ap.parse_args()

    site = config.SITE
    fan_on: dict[str, bool] = {}

    c = config.make_client(client_id="controller")
    c.will_set(config.node_topic("core", "controller", "status"), "offline", qos=1, retain=True)

    def alert(client, level, text, **extra):
        msg = {"ts": time.time(), "level": level, "text": text, **extra}
        client.publish(config.alerts_topic(), json.dumps(msg), qos=2)
        print(f"[controller] ALERT {level}: {text}")

    def on_connect(client, userdata, flags, rc, props=None):
        print(f"[controller] connected rc={rc}")
        client.publish(config.node_topic("core", "controller", "status"), "online",
                       qos=1, retain=True)
        client.subscribe([(f"{config.ROOT}/{site}/+/+/telemetry", 1),
                          (f"{config.ROOT}/{site}/+/+/status", 1)])

    def on_message(client, userdata, msg):
        parsed = config.parse_node_topic(msg.topic)
        if not parsed:
            return
        _, room, node, kind = parsed
        if room == "core":
            return
        if kind == "status":
            if msg.payload == b"offline" and not msg.retain:
                alert(client, "warning", f"вузол {room}/{node} офлайн", room=room, node=node)
            return
        try:
            data = json.loads(msg.payload)
            t = float(data["temperature"])
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            return
        on = fan_on.get(room, False)
        want = True if t > args.on else False if t < args.off else on
        if want != on:
            fan_on[room] = want
            cmd = {"power": "on" if want else "off", "reason": f"t={t:.1f}°C"}
            client.publish(config.node_topic(room, args.fan_prefix + room, "cmd"), json.dumps(cmd), qos=1)
            if want and t > args.on + 5:
                alert(client, "critical", f"перегрів у {room}: {t:.1f}°C", room=room, value=t)

    c.on_connect = on_connect
    c.on_message = on_message

    running = {"v": True}
    signal.signal(signal.SIGINT, lambda *_: running.update(v=False))
    signal.signal(signal.SIGTERM, lambda *_: running.update(v=False))
    config.connect(c)
    c.loop_start()
    while running["v"]:
        time.sleep(0.2)
    c.publish(config.node_topic("core", "controller", "status"), "offline",
              qos=1, retain=True).wait_for_publish(2)
    c.disconnect()
    c.loop_stop()


if __name__ == "__main__":
    main()
