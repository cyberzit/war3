#!/bin/bash
# Initial deployment only; never reloads or modifies existing website services.
set -euo pipefail
test "$(id -u)" = 0
test ! -e /etc/systemd/system/mongolranger.service
test ! -e /var/lib/mongolranger
test ! -e /opt/mongolranger/venv
if ss -H -lnt 'sport = :8050' | grep -q .; then
  echo 'Port 8050 is occupied; no deployment performed.' >&2
  exit 1
fi
test "$(sha256sum /etc/caddy/Caddyfile | cut -d' ' -f1)" = d4218909f8dfb626a4e9109abc91d866345116fc3ec817ffed5fa1a3285b4612
if getent passwd mongolranger >/dev/null; then
  echo 'Account exists unexpectedly; inspect before deployment.' >&2
  exit 1
fi

python3 -m venv --without-pip /opt/mongolranger/venv
curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
  https://bootstrap.pypa.io/pip/pip.pyz -o /opt/mongolranger/pip.pyz
python3 /opt/mongolranger/pip.pyz --python /opt/mongolranger/venv/bin/python \
  install --no-cache-dir -r /opt/mongolranger/app/backend/requirements.lock
cd /opt/mongolranger/app
/opt/mongolranger/venv/bin/python -m unittest backend.test_app -v

useradd --system --no-create-home --home-dir /var/lib/mongolranger --shell /usr/sbin/nologin mongolranger
install -d -o root -g mongolranger -m 0750 /opt/mongolranger/tls
install -d -o root -g root -m 0700 /opt/mongolranger/ca
openssl req -x509 -newkey rsa:3072 -nodes -days 3650 \
  -keyout /opt/mongolranger/ca/ca.key -out /opt/mongolranger/ca/ca.crt \
  -subj '/CN=MongolRanger private service CA' \
  -addext 'basicConstraints=critical,CA:TRUE' \
  -addext 'keyUsage=critical,keyCertSign,cRLSign' 2>/dev/null
openssl req -new -newkey rsa:3072 -nodes \
  -keyout /opt/mongolranger/tls/server.key -out /opt/mongolranger/tls/server.csr \
  -subj '/CN=MongolRanger lobby' 2>/dev/null
cat > /opt/mongolranger/tls/extensions.cnf <<'EOF'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=IP:37.27.115.231
EOF
openssl x509 -req -days 365 -sha256 \
  -in /opt/mongolranger/tls/server.csr \
  -CA /opt/mongolranger/ca/ca.crt -CAkey /opt/mongolranger/ca/ca.key -CAcreateserial \
  -out /opt/mongolranger/tls/server.crt -extfile /opt/mongolranger/tls/extensions.cnf
chmod 0600 /opt/mongolranger/ca/ca.key
chown root:mongolranger /opt/mongolranger/tls/server.key
chmod 0640 /opt/mongolranger/tls/server.key
chmod 0644 /opt/mongolranger/tls/server.crt
install -m 0644 /opt/mongolranger/deploy/mongolranger.service /etc/systemd/system/mongolranger.service
systemd-analyze verify /etc/systemd/system/mongolranger.service
systemctl daemon-reload
systemctl enable --now mongolranger.service
for attempt in 1 2 3 4 5; do
  if curl --fail --silent --show-error --max-time 5 \
      --cacert /opt/mongolranger/ca/ca.crt https://37.27.115.231:8050/healthz; then
    echo
    exit 0
  fi
  sleep 2
done
systemctl disable --now mongolranger.service
echo 'New service failed its health check and has been stopped. Website services were not touched.' >&2
exit 1
