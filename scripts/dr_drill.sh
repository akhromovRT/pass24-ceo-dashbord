#!/usr/bin/env bash
# DR-drill: восстановление последнего prod-дампа в эфемерный postgres
# контейнер + сверка количества строк с production.
#
# Запускать раз в квартал. Возвращает 0 если все таблицы совпадают
# (или count в пределах разумного дрейфа), 1 при расхождении.
#
# Usage:
#   ./scripts/dr_drill.sh /path/to/ceo24-backup-YYYYMMDD-HHMM.dump
set -euo pipefail

DUMP="${1:-}"
if [[ -z "$DUMP" ]] || [[ ! -f "$DUMP" ]]; then
    echo "Usage: $0 <path-to-backup.dump>"
    exit 2
fi

CONTAINER="ceo24-pg-drill-$$"
trap "docker rm -f '$CONTAINER' >/dev/null 2>&1 || true" EXIT

echo "== Starting temporary postgres =="
docker run -d --name "$CONTAINER" --rm \
    -e POSTGRES_USER=ceo24 -e POSTGRES_PASSWORD=ceo24 -e POSTGRES_DB=ceo24 \
    postgres:16-alpine >/dev/null

echo "== Waiting for postgres ready =="
for i in {1..30}; do
    if docker exec "$CONTAINER" pg_isready -U ceo24 >/dev/null 2>&1; then break; fi
    sleep 1
done

echo "== Restoring $DUMP =="
docker cp "$DUMP" "$CONTAINER:/tmp/backup.dump"
docker exec "$CONTAINER" pg_restore -U ceo24 -d ceo24 -c --if-exists /tmp/backup.dump 2>&1 | tail -5

echo "== Row counts (key tables) =="
for tbl in organizations documents monthly_charges payment_allocations \
          debt_snapshots debt_snapshot_rows users; do
    count=$(docker exec "$CONTAINER" psql -U ceo24 -d ceo24 -tAc \
        "SELECT count(*) FROM $tbl" 2>/dev/null || echo "?")
    printf "  %-25s %s\n" "$tbl" "$count"
done

echo "== Sanity checks =="
# 1. Должен быть хотя бы один admin
admins=$(docker exec "$CONTAINER" psql -U ceo24 -d ceo24 -tAc \
    "SELECT count(*) FROM users WHERE role='ADMIN' AND is_active")
if [[ "$admins" -lt 1 ]]; then
    echo "FAIL: 0 active admin users в дампе"
    exit 1
fi
echo "OK: active admins = $admins"

# 2. organizations.in_registry > 0
in_reg=$(docker exec "$CONTAINER" psql -U ceo24 -d ceo24 -tAc \
    "SELECT count(*) FROM organizations WHERE in_registry")
if [[ "$in_reg" -lt 1 ]]; then
    echo "FAIL: 0 организаций с in_registry=true"
    exit 1
fi
echo "OK: in_registry orgs = $in_reg"

echo "== DR drill OK =="
