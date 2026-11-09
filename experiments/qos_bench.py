"""Вимірювання доставки та затримки для QoS 0/1/2 на заданому брокері.

Тест 1 - "онлайн": підписник на зв'язку, видавець шле N повідомлень із заданою
частотою. Міряємо: доставлено/втрачено, дублікати, порушення порядку, затримку
(видавець і підписник на одному ПК - годинник спільний), пропускну здатність.

Тест 2 - "офлайн" (--offline): підписник з persistent session (clean_session=False)
підписується і відключається; видавець шле N повідомлень; підписник повертається.
Показує, що брокер зберігає для офлайн-клієнта лише QoS 1/2.

Приклад:
    python -m experiments.qos_bench --host 127.0.0.1 -n 500 --rate 200
    python -m experiments.qos_bench --host test.mosquitto.org --offline
"""
import argparse
import json
import statistics
import struct
import threading
import time
import uuid

import paho.mqtt.client as mqtt

HDR = struct.Struct("!Iq")  # seq (uint32), час відправки у нс (int64)


def _client(cid, clean=True):
    return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid, clean_session=clean)


def _connect(c, host, port, timeout=10):
    ev = threading.Event()
    c.on_connect = lambda *a, **k: ev.set()
    c.connect(host, port, keepalive=30)
    c.loop_start()
    if not ev.wait(timeout):
        raise TimeoutError(f"no CONNACK from {host}:{port}")


def _pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def run_online(host, port, qos, n=200, rate=100.0, size=64, timeout=30.0):
    topic = f"bench/{uuid.uuid4().hex[:10]}/q{qos}"
    got, lat, lock = [], [], threading.Lock()
    done = threading.Event()
    subscribed = threading.Event()

    sub = _client(f"bench-sub-{uuid.uuid4().hex[:6]}")

    def on_message(c, u, m):
        now = time.time_ns()
        seq, ts = HDR.unpack_from(m.payload)
        with lock:
            got.append(seq)
            lat.append((now - ts) / 1e6)
            if len(got) >= n:
                done.set()

    sub.on_message = on_message
    sub.on_subscribe = lambda *a, **k: subscribed.set()
    _connect(sub, host, port)
    sub.subscribe(topic, qos=qos)
    if not subscribed.wait(10):
        raise TimeoutError("no SUBACK")

    pub = _client(f"bench-pub-{uuid.uuid4().hex[:6]}")
    _connect(pub, host, port)
    pad = b"x" * max(0, size - HDR.size)
    period = 1.0 / rate if rate > 0 else 0
    infos = []
    t_start = time.perf_counter()
    for seq in range(n):
        infos.append(pub.publish(topic, HDR.pack(seq, time.time_ns()) + pad, qos=qos))
        if period:
            target = t_start + (seq + 1) * period
            delay = target - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
    for i in infos:                 # для QoS1/2: чекаємо PUBACK / PUBCOMP
        i.wait_for_publish(timeout)
    t_pub = time.perf_counter() - t_start
    done.wait(timeout)
    time.sleep(0.5)                 # дати шанс прийти дублікатам
    pub.disconnect(); pub.loop_stop()
    sub.disconnect(); sub.loop_stop()

    with lock:
        uniq = set(got)
        ooo = sum(1 for a, b in zip(got, got[1:]) if b < a)
        return {
            "test": "online", "broker": f"{host}:{port}", "qos": qos, "sent": n,
            "received": len(uniq), "lost_pct": round(100 * (n - len(uniq)) / n, 2),
            "duplicates": len(got) - len(uniq), "out_of_order": ooo,
            "lat_min_ms": round(min(lat), 2) if lat else None,
            "lat_p50_ms": round(statistics.median(lat), 2) if lat else None,
            "lat_p95_ms": round(_pct(lat, 95), 2) if lat else None,
            "lat_max_ms": round(max(lat), 2) if lat else None,
            "pub_rate_msg_s": round(n / t_pub, 1),
        }


def run_offline(host, port, qos, n=50, timeout=15.0):
    topic = f"bench/{uuid.uuid4().hex[:10]}/off{qos}"
    sub_id = f"bench-off-{uuid.uuid4().hex[:6]}"

    # 1) підписник створює persistent session і відключається
    sub = _client(sub_id, clean=False)
    ev = threading.Event()
    sub.on_subscribe = lambda *a, **k: ev.set()
    _connect(sub, host, port)
    sub.subscribe(topic, qos=qos)
    ev.wait(10)
    sub.disconnect(); sub.loop_stop()
    time.sleep(0.5)

    # 2) публікація, поки підписник офлайн
    pub = _client(f"bench-pub-{uuid.uuid4().hex[:6]}")
    _connect(pub, host, port)
    for seq in range(n):
        pub.publish(topic, HDR.pack(seq, time.time_ns()), qos=qos).wait_for_publish(timeout)
    pub.disconnect(); pub.loop_stop()

    # 3) підписник повертається з тим самим client_id
    got = []
    sub = _client(sub_id, clean=False)
    sub.on_message = lambda c, u, m: got.append(HDR.unpack_from(m.payload)[0])
    session = {}
    ev = threading.Event()

    def on_connect(c, u, flags, rc, props=None):
        session["present"] = flags.session_present
        ev.set()
    sub.on_connect = on_connect
    sub.connect(host, port, keepalive=30)
    sub.loop_start()
    ev.wait(10)
    t_end = time.time() + 5
    while time.time() < t_end and len(set(got)) < n:
        time.sleep(0.1)
    time.sleep(0.5)
    # прибрати сесію на брокері
    sub.disconnect(); sub.loop_stop()
    cleanup = _client(sub_id, clean=True)
    try:
        _connect(cleanup, host, port)
        cleanup.disconnect(); cleanup.loop_stop()
    except Exception:  # noqa: BLE001
        pass
    return {"test": "offline", "broker": f"{host}:{port}", "qos": qos, "sent": n,
            "received": len(set(got)), "lost_pct": round(100 * (n - len(set(got))) / n, 2),
            "session_present": session.get("present")}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--qos", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("-n", type=int, default=200)
    ap.add_argument("--rate", type=float, default=100, help="повідомлень/с (0 = макс.)")
    ap.add_argument("--size", type=int, default=64, help="розмір payload, байт")
    ap.add_argument("--offline", action="store_true", help="тест офлайн-підписника")
    args = ap.parse_args()
    for q in args.qos:
        r = (run_offline(args.host, args.port, q, min(args.n, 50)) if args.offline
             else run_online(args.host, args.port, q, args.n, args.rate, args.size))
        print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
