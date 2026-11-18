#!/usr/bin/env bash
# Install or update MeetingMinutes on the (offline) server from a bundle made by build-bundle.
# Keeps .env, ./models and ./data of an existing installation.
#   sudo deploy/install-bundle.sh                       # installs into /opt/meetingminutes
#   sudo deploy/install-bundle.sh /srv/meetingminutes
set -euo pipefail

BUNDLE="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-/opt/meetingminutes}"
# shellcheck source=/dev/null
source "$BUNDLE/bundle.env"   # TAG, OLLAMA_VERSION, PLATFORM

echo "==> loading images ($PLATFORM, tag $TAG) - this takes a few minutes"
docker load -i "$BUNDLE/images.tar"

mkdir -p "$TARGET/deploy" "$TARGET/models" "$TARGET/data"
if [[ ! "$BUNDLE" -ef "$TARGET" ]]; then
    cp "$BUNDLE"/docker-compose.yml "$BUNDLE"/docker-compose.cpu.yml "$BUNDLE"/.env.example "$BUNDLE"/README.md "$TARGET/"
    cp "$BUNDLE"/deploy/* "$TARGET/deploy/"
    cp "$BUNDLE"/models/README.md "$TARGET/models/"
fi

ENV_FILE="$TARGET/.env"
[[ -f "$ENV_FILE" ]] || cp "$TARGET/.env.example" "$ENV_FILE"
set_env() { # <key> <value>
    if grep -qE "^$1=" "$ENV_FILE"; then sed -i "s|^$1=.*|$1=$2|" "$ENV_FILE"; else echo "$1=$2" >> "$ENV_FILE"; fi
}
previous_tag="$(grep -E '^TAG=' "$ENV_FILE" | cut -d= -f2 || true)"
set_env TAG "$TAG"
set_env OLLAMA_VERSION "$OLLAMA_VERSION"

cd "$TARGET"
docker compose up -d --no-build --pull never --remove-orphans
docker compose ps

echo
echo "Installed version $TAG into $TARGET."
if [[ -n "$previous_tag" && "$previous_tag" != "$TAG" ]]; then
    echo "Rollback: set TAG=$previous_tag in $ENV_FILE and run 'docker compose up -d' in $TARGET."
fi
echo "Check: curl -k https://localhost/api/health"
