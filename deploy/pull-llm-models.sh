#!/usr/bin/env bash
# Pull LLMs into the bundled Ollama (stored in ./data/ollama). Needs internet - run it during
# the online setup phase. Default: the models offered in the UI settings dialog.
#   deploy/pull-llm-models.sh
#   deploy/pull-llm-models.sh gemma3:12b llama3.1:8b
set -euo pipefail
cd "$(dirname "$0")/.."

models=("$@")
if [[ ${#models[@]} -eq 0 ]]; then models=(gemma3:12b gemma3:4b qwen2.5:14b); fi

docker compose up -d ollama
echo "==> waiting for Ollama"
for _ in $(seq 60); do
    if docker compose exec -T ollama ollama list >/dev/null 2>&1; then break; fi
    sleep 1
done

for model in "${models[@]}"; do
    echo "==> pulling $model"
    docker compose exec -T ollama ollama pull "$model"
done
docker compose exec -T ollama ollama list
