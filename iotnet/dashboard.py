"""Термінальна панель (підписник на iot/<site>/#).

Показує таблицю всіх вузлів: статус (з retained/LWT), останні виміри, стан
виконавців та останні тривоги. Оновлюється раз на секунду.

Приклад:  python -m iotnet.dashboard
"""
import json
import signal
import time
from collections import deque

from . import config

CLEAR = "\033[2J\033[H"
RED, GREEN, YEL, DIM, RST = "\033[31m", "\033[32m", "\033[33m", "\033[2m", "\033[0m"


def main():
    nodes: dict[str, dict] = {}
    alerts: deque = deque(maxlen=5)
    stats = {"msgs": 0}

    c = config.make_client(client_id="dashboard")

    def on_connect(client, userdata, flags, rc, props=None):
        client.subscribe(f"{config.ROOT}/{config.SITE}/#", qos=1)

    def on_message(client, userdata, msg):
        stats["msgs"] += 1
        if msg.topic == config.alerts_topic():
            try:
                alerts.appendleft(json.loads(msg.payload))
            except json.JSONDecodeError:
                pass
            return
        parsed = config.parse_node_topic(msg.topic)
        if not parsed:
            return
        _, room, node, kind = parsed
        n = nodes.setdefault(f"{room}/{node}", {})
        if kind == "status":
            n["status"] = msg.payload.decode()
        elif kind in ("telemetry", "state"):
            try:
                n[kind] = json.loads(msg.payload)
                n["seen"] = time.time()
            except json.JSONDecodeError:
                pass

    c.on_connect = on_connect
    c.on_message = on_message

    running = {"v": True}
    signal.signal(signal.SIGINT, lambda *_: running.update(v=False))
    config.connect(c)
    c.loop_start()
    while running["v"]:
        out = [CLEAR, f"IoT MQTT dashboard  broker={config.BROKER_HOST}:{config.BROKER_PORT}"
               f"  site={config.SITE}  msgs={stats['msgs']}\n"]
        out.append(f"{'NODE':<24}{'STATUS':<10}{'T,°C':>8}{'RH,%':>8}{'P,hPa':>9}"
                   f"{'SEQ':>7}  STATE")
        for key in sorted(nodes):
            n = nodes[key]
            st = n.get("status", "?")
            col = GREEN if st == "online" else RED if st == "offline" else YEL
            tel = n.get("telemetry", {})
            stt = n.get("state")
            age = time.time() - n.get("seen", 0)
            line = (f"{key:<24}{col}{st:<10}{RST}"
                    f"{tel.get('temperature', ''):>8}{tel.get('humidity', ''):>8}"
                    f"{tel.get('pressure', ''):>9}{tel.get('seq', ''):>7}  ")
            if stt:
                p = stt.get("power")
                line += f"{GREEN if p == 'on' else DIM}fan {p}{RST}"
            if tel and age > 10:
                line += f" {YEL}(нема даних {age:.0f}s){RST}"
            out.append(line)
        out.append("\nОстанні тривоги:")
        for a in alerts:
            col = RED if a.get("level") == "critical" else YEL
            out.append(f"  {time.strftime('%H:%M:%S', time.localtime(a.get('ts', 0)))} "
                       f"{col}{a.get('level')}{RST}: {a.get('text')}")
        print("\n".join(out), flush=True)
        time.sleep(1)
    c.disconnect()
    c.loop_stop()


if __name__ == "__main__":
    main()
