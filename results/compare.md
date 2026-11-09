# Порівняння брокерів (2026-11-09 09:22, n=200, rate=50.0 msg/s)

## Онлайн-доставка

| Брокер | QoS | Отримано | Втрати % | Дублі | p50, мс | p95, мс | max, мс | msg/s |
|---|---|---|---|---|---|---|---|---|
| local | 0 | 200 | 0.0 | 0 | 2.14 | 3.59 | 21.84 | 50.0 |
| local | 1 | 200 | 0.0 | 0 | 2.32 | 3.79 | 5.27 | 50.0 |
| local | 2 | 200 | 0.0 | 0 | 4.63 | 8.22 | 12.22 | 50.0 |
| test.mosquitto.org | 0 |  |  |  |  |  |  |  ⚠ TimeoutError: no CONNACK from test.mosquitto.org:1883 |
| test.mosquitto.org | 1 |  |  |  |  |  |  |  ⚠ TimeoutError: no CONNACK from test.mosquitto.org:1883 |
| test.mosquitto.org | 2 |  |  |  |  |  |  |  ⚠ TimeoutError: no CONNACK from test.mosquitto.org:1883 |
| broker.hivemq.com | 0 | 200 | 0.0 | 0 | 78.82 | 102.1 | 137.1 | 50.0 |
| broker.hivemq.com | 1 | 200 | 0.0 | 0 | 153.28 | 228.38 | 249.78 | 49.2 |
| broker.hivemq.com | 2 | 200 | 0.0 | 0 | 298.29 | 392.15 | 407.67 | 47.9 |
| broker.emqx.io | 0 | 40 | 80.0 | 0 | 302.84 | 392.83 | 418.24 | 50.0 |
| broker.emqx.io | 1 | 40 | 80.0 | 0 | 222.1 | 252.66 | 255.76 | 49.3 |
| broker.emqx.io | 2 | 70 | 65.0 | 0 | 1987.88 | 3947.93 | 3993.21 | 24.7 |

## Офлайн-підписник (persistent session, 50 повідомлень)

| Брокер | QoS | Отримано після повернення | Сесія збережена |
|---|---|---|---|
| local | 0 | 0 | False |
| local | 1 | 0 | True |
| local | 2 | 0 | False |
| test.mosquitto.org | 0 |  |  ⚠ TimeoutError: no CONNACK from test.mosquitto.org:1883 |
| test.mosquitto.org | 1 |  |  ⚠ TimeoutError: no CONNACK from test.mosquitto.org:1883 |
| test.mosquitto.org | 2 |  |  ⚠ TimeoutError: no CONNACK from test.mosquitto.org:1883 |
| broker.hivemq.com | 0 | 0 | True |
| broker.hivemq.com | 1 | 50 | True |
| broker.hivemq.com | 2 | 50 | True |
| broker.emqx.io | 0 | 10 | True |
| broker.emqx.io | 1 | 50 | True |
| broker.emqx.io | 2 | 50 | True |
