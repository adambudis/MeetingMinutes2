#!/bin/sh
# Runs on every container start (nginx image entrypoint hook).
#
# Creates a self-signed TLS certificate for $SERVER_HOSTS (comma-separated host names / IPs)
# in /certs, and re-creates it whenever SERVER_HOSTS changes.
# To use your own certificate instead, put server.crt + server.key into the certs volume and
# delete the .generated-for marker file: certificates without the marker are never touched.
set -eu

CERT_DIR=/certs
CRT="$CERT_DIR/server.crt"
KEY="$CERT_DIR/server.key"
MARKER="$CERT_DIR/.generated-for"
HOSTS="${SERVER_HOSTS:-localhost}"

mkdir -p "$CERT_DIR"

if [ -f "$CRT" ] && [ -f "$KEY" ]; then
    if [ ! -f "$MARKER" ]; then
        echo "cert: using the provided certificate $CRT"
        exit 0
    fi
    if [ "$(cat "$MARKER")" = "$HOSTS" ]; then
        echo "cert: self-signed certificate for '$HOSTS' is up to date"
        exit 0
    fi
fi

SAN="DNS:localhost,IP:127.0.0.1"
CN=""
OLD_IFS=$IFS
IFS=','
for host in $HOSTS; do
    host=$(echo "$host" | tr -d ' ')
    [ -z "$host" ] && continue
    [ -z "$CN" ] && CN="$host"
    if echo "$host" | grep -Eq '^[0-9]+(\.[0-9]+){3}$' || echo "$host" | grep -q ':'; then
        SAN="$SAN,IP:$host"
    else
        SAN="$SAN,DNS:$host"
    fi
done
IFS=$OLD_IFS
[ -z "$CN" ] && CN=localhost

echo "cert: generating self-signed certificate (CN=$CN, $SAN)"
if ! output=$(openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 3650 \
    -keyout "$KEY" -out "$CRT" \
    -subj "/CN=$CN/O=MeetingMinutes" \
    -addext "subjectAltName=$SAN" \
    -addext "basicConstraints=critical,CA:FALSE" \
    -addext "extendedKeyUsage=serverAuth" 2>&1); then
    echo "cert: openssl failed:" >&2
    echo "$output" >&2
    exit 1
fi
chmod 600 "$KEY"
printf '%s' "$HOSTS" > "$MARKER"
