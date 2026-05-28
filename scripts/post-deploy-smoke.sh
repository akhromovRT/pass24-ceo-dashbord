#!/usr/bin/env bash
# Post-deploy smoke test: после docker compose up -d убедиться, что прод живой
# и не отдаёт ничего без авторизации.
#
# Используется руками или в pre-deploy pipeline. Возвращает 0 при успехе,
# 1 при любом провале.
set -euo pipefail

HOST="${1:-https://ceo.pass24pro.ru}"
echo "== smoke ${HOST} =="

# 1. Frontend отдаёт 200
code=$(curl -s -o /dev/null -w "%{http_code}" "${HOST}/")
if [[ "$code" != "200" ]]; then
    echo "FAIL: frontend / returned $code, expected 200"; exit 1
fi
echo "OK: frontend / 200"

# 2. Защищённый эндпоинт без токена → 401 (а не 200, не 500, не 403)
code=$(curl -s -o /dev/null -w "%{http_code}" "${HOST}/api/v1/dashboard/summary")
if [[ "$code" != "401" ]]; then
    echo "FAIL: /api/v1/dashboard/summary без токена вернул $code (ожидали 401)"
    exit 1
fi
echo "OK: /api/v1/dashboard/summary 401"

# 3. /api/v1/docs в проде должен быть 404 (закрыт, если DEBUG=false).
# Без префикса /api/ путь /docs ловит SPA-fallback nginx и отдаёт index.html
# с кодом 200 — это норма, не сигнал что docs открыт.
code=$(curl -s -o /dev/null -w "%{http_code}" "${HOST}/api/v1/docs")
if [[ "$code" != "404" ]]; then
    echo "FAIL: /api/v1/docs вернул $code (ожидали 404 — DEBUG=true в проде?)"
    exit 1
fi
echo "OK: /api/v1/docs 404"
code=$(curl -s -o /dev/null -w "%{http_code}" "${HOST}/openapi.json")
if [[ "$code" != "404" ]]; then
    echo "WARN: /openapi.json вернул $code (ожидали 404 — это SPA-fallback или DEBUG=true?)"
fi

# 4. /healthz контейнера фронтенда (внутренний путь)
code=$(curl -s -o /dev/null -w "%{http_code}" "${HOST}/healthz")
if [[ "$code" != "200" ]]; then
    echo "FAIL: /healthz вернул $code"; exit 1
fi
echo "OK: /healthz 200"

echo "== smoke OK =="
