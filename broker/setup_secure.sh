#!/usr/bin/env bash
# Генерує паролі та TLS-сертифікати для mosquitto-secure.conf
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p secure ../data/mosquitto
PASS="${IOT_PASS:-iot-demo-pass}"

rm -f secure/passwd
for u in controller dashboard logger bench t-kitchen t-bedroom fan-kitchen fan-bedroom; do
  mosquitto_passwd -b $([ -f secure/passwd ] || echo -c) secure/passwd "$u" "$PASS"
done
chmod 600 secure/passwd

# власний CA + серверний сертифікат (самопідписані - для навчального стенду)
openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=iot-demo-ca" \
  -keyout secure/ca.key -out secure/ca.crt 2>/dev/null
openssl req -newkey rsa:2048 -nodes -subj "/CN=localhost" \
  -keyout secure/server.key -out secure/server.csr 2>/dev/null
openssl x509 -req -in secure/server.csr -CA secure/ca.crt -CAkey secure/ca.key \
  -CAcreateserial -days 365 -out secure/server.crt \
  -extfile <(printf "subjectAltName=DNS:localhost,IP:127.0.0.1") 2>/dev/null
echo "Готово. Користувачі мають пароль: $PASS"
