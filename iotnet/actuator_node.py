"""Вузол-підписник/виконавець: віртуальний вентилятор (реле).

Підписується на iot/<site>/<room>/<node>/cmd і виконує JSON-команди
{"power": "on"|"off"}. Свій стан публікує retained у .../state.

Приклад:  python -m iotnet.actuator_node --room kitchen --node fan-kitchen
"""
import argparse
import json
import signal
import time

from . import config


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--room", default="livingroom")
    ap.add_argument("--node", default="fan-livingroom")
    args = ap.parse_args()

    status_t = config.node_topic(args.room, args.node, "status")
    state_t = config.node_topic(args.room, args.node, "state")
    cmd_t = config.node_topic(args.room, args.node, "cmd")
    state = {"power": "off", "changed": time.time()}

    # clean_session=False + QoS1: команди, надіслані поки вузол офлайн, будуть доставлені
    c = config.make_client(client_id=f"{args.room}-{args.node}", clean_session=False)
    c.will_set(status_t, "offline", qos=1, retain=True)

    def publish_state(client):
        client.publish(state_t, json.dumps(state), qos=1, retain=True)

    def on_connect(client, userdata, flags, rc, props=None):
        print(f"[{args.node}] connected rc={rc} session_present={flags.session_present}")
        client.publish(status_t, "online", qos=1, retain=True)
        client.subscribe(cmd_t, qos=1)
        publish_state(client)

    def on_message(client, userdata, msg):
        if msg.topic != cmd_t:   # захист від чужих повідомлень (див. README, amqtt)
            return
        try:
            cmd = json.loads(msg.payload)
            power = cmd["power"]
            if power not in ("on", "off"):
                raise ValueError(power)
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            print(f"[{args.node}] invalid command on {msg.topic}: {msg.payload!r}")
            return
        if power != state["power"]:
            state.update(power=power, changed=time.time(),
                         reason=cmd.get("reason", ""))
            print(f"[{args.node}] power -> {power} ({cmd.get('reason', '')})")
            publish_state(client)

    c.on_connect = on_connect
    c.on_message = on_message

    running = {"v": True}
    signal.signal(signal.SIGINT, lambda *_: running.update(v=False))
    signal.signal(signal.SIGTERM, lambda *_: running.update(v=False))

    config.connect(c)
    c.loop_start()
    while running["v"]:
        time.sleep(0.2)
    c.publish(status_t, "offline", qos=1, retain=True).wait_for_publish(2)
    c.disconnect()
    c.loop_stop()


if __name__ == "__main__":
    main()
