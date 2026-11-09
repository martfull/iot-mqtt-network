"""Вузол-видавець: віртуальний датчик температури/вологості/тиску.

Демонструє:
  * періодичну публікацію телеметрії (JSON) з вибраним QoS;
  * Last Will and Testament: брокер сам опублікує "offline", якщо вузол зник;
  * retained-статус "online", щоб нові підписники одразу бачили стан вузла;
  * прийом команд (cmd), наприклад зміна інтервалу публікації.

Приклад:  python -m iotnet.sensor_node --room kitchen --node t-kitchen --interval 2
"""
import argparse
import json
import math
import random
import signal
import time

from . import config


class SimSensor:
    """Правдоподібні показники: добовий синусоїдальний хід + шум + рідкі сплески."""

    def __init__(self, base_temp: float, seed: int | None = None):
        self.rng = random.Random(seed)
        self.base = base_temp
        self.t0 = time.time()
        self.spike = 0.0

    def read(self) -> dict:
        t = time.time() - self.t0
        # «добу» стиснуто до 10 хв, щоб зміни було видно на демонстрації
        day = math.sin(2 * math.pi * t / 600)
        if self.rng.random() < 0.02:          # позаштатна подія: різкий нагрів
            self.spike = self.rng.uniform(6, 10)
        self.spike *= 0.9
        temp = self.base + 3 * day + self.spike + self.rng.gauss(0, 0.2)
        hum = 50 - 8 * day + self.rng.gauss(0, 1.0)
        pres = 1013 + 2 * math.sin(2 * math.pi * t / 1800) + self.rng.gauss(0, 0.3)
        return {"temperature": round(temp, 2),
                "humidity": round(min(max(hum, 0), 100), 1),
                "pressure": round(pres, 1)}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--room", default="livingroom")
    ap.add_argument("--node", default="t-livingroom")
    ap.add_argument("--interval", type=float, default=2.0, help="секунди між публікаціями")
    ap.add_argument("--qos", type=int, choices=[0, 1, 2], default=0)
    ap.add_argument("--base-temp", type=float, default=22.0)
    ap.add_argument("--seed", type=int)
    args = ap.parse_args()

    status_t = config.node_topic(args.room, args.node, "status")
    tele_t = config.node_topic(args.room, args.node, "telemetry")
    cmd_t = config.node_topic(args.room, args.node, "cmd")

    sensor = SimSensor(args.base_temp, args.seed)
    state = {"interval": args.interval, "seq": 0, "running": True}

    c = config.make_client(client_id=f"{args.room}-{args.node}")
    c.will_set(status_t, "offline", qos=1, retain=True)

    def on_connect(client, userdata, flags, rc, props=None):
        print(f"[{args.node}] connected rc={rc}")
        client.publish(status_t, "online", qos=1, retain=True)
        client.subscribe(cmd_t, qos=1)

    def on_message(client, userdata, msg):
        if msg.topic != cmd_t:   # захист від чужих повідомлень (див. README, amqtt)
            return
        try:
            cmd = json.loads(msg.payload)
        except json.JSONDecodeError:
            print(f"[{args.node}] bad command on {msg.topic}: {msg.payload!r}")
            return
        if "interval" in cmd:
            state["interval"] = max(0.1, float(cmd["interval"]))
            print(f"[{args.node}] interval -> {state['interval']}s")

    c.on_connect = on_connect
    c.on_message = on_message

    def stop(*_):
        state["running"] = False
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    config.connect(c)
    c.loop_start()
    try:
        while state["running"]:
            state["seq"] += 1
            payload = {"node": args.node, "room": args.room, "seq": state["seq"],
                       "ts": time.time(), **sensor.read()}
            c.publish(tele_t, json.dumps(payload), qos=args.qos)
            time.sleep(state["interval"])
    finally:
        # коректне вимкнення: LWT не спрацює, тому публікуємо offline самі
        c.publish(status_t, "offline", qos=1, retain=True).wait_for_publish(2)
        c.disconnect()
        c.loop_stop()
        print(f"[{args.node}] stopped")


if __name__ == "__main__":
    main()
