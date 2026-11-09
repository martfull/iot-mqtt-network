"""Порівняння приватного (локального) та публічних MQTT-брокерів.

Для кожного брокера і кожного QoS запускає онлайн- та офлайн-тести з
qos_bench і зберігає результати в results/compare.csv та results/compare.md.

Приклад:
    python -m experiments.compare_brokers                # локальний + 3 публічні
    python -m experiments.compare_brokers --only local
"""
import argparse
import csv
import os
import time

from .qos_bench import run_offline, run_online

BROKERS = {
    "local": ("127.0.0.1", 1883),
    "test.mosquitto.org": ("test.mosquitto.org", 1883),
    "broker.hivemq.com": ("broker.hivemq.com", 1883),
    "broker.emqx.io": ("broker.emqx.io", 1883),
}

COLS = ["name", "test", "qos", "sent", "received", "lost_pct", "duplicates",
        "out_of_order", "lat_min_ms", "lat_p50_ms", "lat_p95_ms", "lat_max_ms",
        "pub_rate_msg_s", "session_present", "error"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+", choices=list(BROKERS), help="лише ці брокери")
    ap.add_argument("-n", type=int, default=200)
    ap.add_argument("--rate", type=float, default=50)
    ap.add_argument("--out", default="results")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    rows = []
    for name in args.only or BROKERS:
        host, port = BROKERS[name]
        for qos in (0, 1, 2):
            for kind in ("online", "offline"):
                print(f"-> {name} QoS{qos} {kind} ...", flush=True)
                try:
                    r = (run_online(host, port, qos, args.n, args.rate) if kind == "online"
                         else run_offline(host, port, qos, 50))
                except Exception as e:  # noqa: BLE001 - публічний брокер може бути недоступний
                    r = {"test": kind, "qos": qos, "error": f"{type(e).__name__}: {e}"}
                r["name"] = name
                rows.append(r)
                print("   ", {k: r.get(k) for k in ("received", "lost_pct", "lat_p50_ms",
                                                    "lat_p95_ms", "error") if r.get(k) is not None})

    with open(os.path.join(args.out, "compare.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    def cell(v):
        return "" if v is None else str(v)
    md = [f"# Порівняння брокерів ({time.strftime('%Y-%m-%d %H:%M')}, n={args.n}, "
          f"rate={args.rate} msg/s)\n",
          "## Онлайн-доставка\n",
          "| Брокер | QoS | Отримано | Втрати % | Дублі | p50, мс | p95, мс | max, мс | msg/s |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["test"] == "online":
            md.append("| " + " | ".join(cell(r.get(k)) for k in (
                "name", "qos", "received", "lost_pct", "duplicates", "lat_p50_ms",
                "lat_p95_ms", "lat_max_ms", "pub_rate_msg_s")) + (f" ⚠ {r['error']}" if r.get("error") else "") + " |")
    md += ["\n## Офлайн-підписник (persistent session, 50 повідомлень)\n",
           "| Брокер | QoS | Отримано після повернення | Сесія збережена |", "|---|---|---|---|"]
    for r in rows:
        if r["test"] == "offline":
            md.append(f"| {r['name']} | {r['qos']} | {cell(r.get('received'))} | "
                      f"{cell(r.get('session_present'))}{' ⚠ ' + r['error'] if r.get('error') else ''} |")
    path = os.path.join(args.out, "compare.md")
    with open(path, "w") as f:
        f.write("\n".join(md) + "\n")
    print(f"\nЗбережено: {path} та compare.csv")


if __name__ == "__main__":
    main()
