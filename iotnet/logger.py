"""Підписник-логер: зберігає всю телеметрію та тривоги в SQLite.

Приклад:  python -m iotnet.logger --db data/telemetry.db
Перегляд:  sqlite3 data/telemetry.db "select * from telemetry order by ts desc limit 10"
"""
import argparse
import json
import os
import signal
import sqlite3
import time

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry(
  ts REAL, room TEXT, node TEXT, seq INTEGER,
  temperature REAL, humidity REAL, pressure REAL, latency_ms REAL);
CREATE TABLE IF NOT EXISTS events(ts REAL, topic TEXT, payload TEXT);
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/telemetry.db")
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.db) or ".", exist_ok=True)
    db = sqlite3.connect(args.db, check_same_thread=False)
    db.executescript(SCHEMA)

    # persistent session: після перезапуску логер отримає пропущені QoS1-повідомлення
    c = config.make_client(client_id="logger", clean_session=False)

    def on_connect(client, userdata, flags, rc, props=None):
        print(f"[logger] connected rc={rc} session_present={flags.session_present}")
        client.subscribe([(f"{config.ROOT}/{config.SITE}/+/+/telemetry", 1),
                          (f"{config.ROOT}/{config.SITE}/+/+/status", 1),
                          (config.alerts_topic(), 2)])

    def on_message(client, userdata, msg):
        now = time.time()
        parsed = config.parse_node_topic(msg.topic)
        if parsed and parsed[3] == "telemetry":
            try:
                d = json.loads(msg.payload)
            except json.JSONDecodeError:
                return
            db.execute("INSERT INTO telemetry VALUES(?,?,?,?,?,?,?,?)",
                       (d.get("ts", now), d.get("room"), d.get("node"), d.get("seq"),
                        d.get("temperature"), d.get("humidity"), d.get("pressure"),
                        (now - d["ts"]) * 1000 if "ts" in d else None))
        else:
            db.execute("INSERT INTO events VALUES(?,?,?)",
                       (now, msg.topic, msg.payload.decode(errors="replace")))
        db.commit()

    c.on_connect = on_connect
    c.on_message = on_message
    running = {"v": True}
    signal.signal(signal.SIGINT, lambda *_: running.update(v=False))
    signal.signal(signal.SIGTERM, lambda *_: running.update(v=False))
    config.connect(c)
    c.loop_start()
    while running["v"]:
        time.sleep(0.2)
    c.disconnect()
    c.loop_stop()
    db.close()


if __name__ == "__main__":
    main()
