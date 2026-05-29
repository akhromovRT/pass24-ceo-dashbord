# Runbook — CEO24 production (85.239.51.34)

Операционные процедуры для восстановления и эксплуатации production-сервиса.

## Доступ

| Что | Как |
|---|---|
| SSH | `ssh ceo24` (alias в `~/.ssh/config`) |
| SSH-ключ | `~/.ssh/ceo24_ed25519` |
| UI | https://ceo.pass24pro.ru |
| Логин | `admin@onvi-service.ru` (пароль — `~/.config/ceo24/credentials`, chmod 600, не в репо) |
| Compose-директория | `/root/pass24-ceo-dashbord/` |
| Backups директория на сервере | `/srv/ceo24/backups/` (ретеншн 14 дней) |
| Backups локально (зеркало) | `~/Backups/ceo24/` (pull в 05:00 через launchd) |
| Backups offsite S3 | `s3://pass24-backups/ceo24/` (TimeWeb, ретеншн 30 дней) |
| Логи бэкапа на сервере | `/var/log/ceo24-backup.log` |
| Секреты S3 | `/etc/ceo24/backup-s3.env` (root:root 600) |

## Сайт не открывается — что делать

### 1. Базовая диагностика
```bash
ping 85.239.51.34                              # хост жив?
curl -sI https://ceo.pass24pro.ru/             # nginx отвечает?
ssh ceo24 'docker ps -a; df -h; free -m'       # контейнеры + диск + память
```

### 2. По симптомам

| Симптом | Действие |
|---|---|
| Ping не проходит | Проблема на стороне Timeweb — идти в их панель |
| Все контейнеры `Up (healthy)`, сайт 5xx | `ssh ceo24 'cd /root/pass24-ceo-dashbord && docker compose logs --tail=100 backend'` |
| Какой-то контейнер `Exited` | `ssh ceo24 'cd /root/pass24-ceo-dashbord && docker compose up -d'` (`restart: unless-stopped` обычно решает сам) |
| Контейнеры отсутствуют | См. «Полное восстановление» ниже |
| `df -h` показывает 100% | `docker system prune -a -f` (внимательно: удалит неиспользуемые образы) |
| `free -m` показывает 0 free + swap полный | `reboot` сервера: `ssh ceo24 reboot` (стек поднимется сам) |

### 3. Логи приложения

```bash
ssh ceo24 'cd /root/pass24-ceo-dashbord && docker compose logs -f backend'
ssh ceo24 'cd /root/pass24-ceo-dashbord && docker compose logs -f frontend'
ssh ceo24 'cd /root/pass24-ceo-dashbord && docker compose logs --since 1h db'
```

## Полное восстановление из бэкапа

Когда: контейнеры удалены, или БД пустая.

```bash
# 1. Подключиться
ssh ceo24

# 2. Если стек удалён — клонировать заново
cd /root && git clone git@github.com:akhromovRT/pass24-ceo-dashbord.git
cd pass24-ceo-dashbord

# 3. Поднять только БД
docker compose up -d db
sleep 15

# 4. Найти последний бэкап
ls -t /srv/ceo24/backups/ceo24-*.dump.gz | head -3

# 5. Восстановить (заменить FILE.gz на актуальный)
gunzip < /srv/ceo24/backups/ceo24-<DATE>.dump.gz | \
  docker exec -i $(docker ps -qf name=db) pg_restore -U ceo24 -d ceo24 --clean --if-exists --no-owner

# 6. Поднять остальные сервисы
docker compose up -d

# 7. Проверка
docker exec $(docker ps -qf name=db) psql -U ceo24 -d ceo24 -c "SELECT COUNT(*) FROM organizations;"
curl -sI https://ceo.pass24pro.ru/
```

Если на ноуте более свежий бэкап (например, серверный диск убит):

```bash
scp ~/Backups/ceo24/ceo24-<latest>.dump.gz ceo24:/tmp/
ssh ceo24 'gunzip < /tmp/ceo24-<latest>.dump.gz | docker exec -i $(docker ps -qf name=db) pg_restore -U ceo24 -d ceo24 --clean --if-exists --no-owner'
```

Если погиб и сервер, и ноут — забрать дамп из S3:

```bash
# на любой машине с aws-cli и ключами из /etc/ceo24/backup-s3.env
set -a; source /etc/ceo24/backup-s3.env; set +a
aws --endpoint-url="$S3_ENDPOINT" s3 ls "s3://$S3_BUCKET/ceo24/" | sort | tail -3
aws --endpoint-url="$S3_ENDPOINT" s3 cp "s3://$S3_BUCKET/ceo24/<latest>" /tmp/
# дальше — обычный pg_restore из шагов выше
```

## Снять дамп вручную (вне cron-расписания)

```bash
ssh ceo24 '/usr/local/bin/ceo24-backup.sh'
ssh ceo24 'ls -lh /srv/ceo24/backups/ | tail -5'
```

Чтобы сразу забрать на ноут:

```bash
~/bin/ceo24-pull-backup.sh
ls -lht ~/Backups/ceo24/ | head -3
```

## Деплой изменений

```bash
# Локально
git add ...
git commit -m "..."
git push origin main

# На сервере
ssh ceo24 'cd /root/pass24-ceo-dashbord && \
  git pull --ff-only origin main && \
  docker compose build && \
  docker compose up -d'
```

Если меняли только backend-код:

```bash
ssh ceo24 'cd /root/pass24-ceo-dashbord && \
  git pull --ff-only origin main && \
  docker compose build backend && \
  docker compose up -d backend'
```

## HTTPS / TLS-сертификат

Сайт обслуживается по HTTPS на домене `ceo.pass24pro.ru`. TLS терминируется в nginx внутри
`frontend`-контейнера. Сертификат — Let's Encrypt.

| Что | Где |
|---|---|
| Сертификат и ключи | `/srv/ceo24/certbot/conf/live/ceo.pass24pro.ru/` |
| Webroot для ACME-проверки | `/srv/ceo24/certbot/www/` |
| Конфиг nginx (HTTP-редирект + HTTPS) | `frontend/nginx.conf` (собран в образ) |
| Автопродление | cron `/etc/cron.d/ceo24-cert-renew`, лог `/var/log/ceo24-cert-renew.log` |

Сертификат монтируется в `frontend`-контейнер двумя bind-mount (`docker-compose.yml`):
`/srv/ceo24/certbot/conf` → `/etc/letsencrypt` (ro), `/srv/ceo24/certbot/www` → `/var/www/certbot` (ro).

### Проверить срок действия

```bash
ssh ceo24 'docker run --rm -v /srv/ceo24/certbot/conf:/etc/letsencrypt certbot/certbot certificates'
```

### Продлить вручную (если автопродление не сработало)

```bash
ssh ceo24 'docker run --rm \
  -v /srv/ceo24/certbot/conf:/etc/letsencrypt \
  -v /srv/ceo24/certbot/www:/var/www/certbot \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d ceo.pass24pro.ru --non-interactive --keep-until-expiring \
  --agree-tos -m akhromov@pass24online.ru && \
  docker exec $(docker ps -qf name=frontend) nginx -s reload'
```

`--keep-until-expiring` — если до истечения далеко, certbot ничего не делает (команду
безопасно запускать часто). После успешного продления nginx перечитывает сертификат.

### Первичный выпуск (если каталог сертификатов утрачен)

```bash
ssh ceo24
mkdir -p /srv/ceo24/certbot/conf /srv/ceo24/certbot/www
cd /root/pass24-ceo-dashbord
docker compose stop frontend                          # порт 80 нужен certbot standalone
docker run --rm -p 80:80 \
  -v /srv/ceo24/certbot/conf:/etc/letsencrypt \
  -v /srv/ceo24/certbot/www:/var/www/certbot \
  certbot/certbot certonly --standalone \
  -d ceo.pass24pro.ru --non-interactive --agree-tos -m akhromov@pass24online.ru
docker compose up -d frontend
```

### Если HTTPS не открывается

| Симптом | Действие |
|---|---|
| Браузер: сертификат истёк | Продлить вручную (см. выше); проверить cron-лог `/var/log/ceo24-cert-renew.log` |
| `frontend` в `Restarting`, в логах nginx «cannot load certificate» | Файлов сертификата нет в `/srv/ceo24/certbot/conf/live/...` — выполнить первичный выпуск |
| HTTP не редиректит на HTTPS | Пересобрать образ с актуальным `nginx.conf`: `docker compose build frontend && docker compose up -d frontend` |

## Состояние подсистем (квик-чек)

```bash
ssh ceo24 'docker compose -f /root/pass24-ceo-dashbord/docker-compose.yml ps; \
  echo "---disk---"; df -h /; \
  echo "---mem---"; free -m; \
  echo "---backups---"; ls -lh /srv/ceo24/backups/ | tail -5; \
  echo "---last cron log---"; tail -5 /var/log/ceo24-backup.log 2>/dev/null'
```

## Управление пользователями

### Через UI (если admin может залогиниться)

Зайти на https://ceo.pass24pro.ru как admin → меню «Пользователи»:
- Создать нового пользователя (имя, email, роль) → диалог покажет сгенерированный пароль один раз
- Сбросить пароль любому пользователю → диалог покажет новый пароль

### Через CLI (если admin не может залогиниться, или для скриптов)

```bash
# Список пользователей
ssh ceo24 'docker exec $(docker ps -qf name=backend) python scripts/manage_users.py list'

# Создать пользователя
ssh ceo24 'docker exec $(docker ps -qf name=backend) python scripts/manage_users.py create \
    --email user@example.ru --name "Имя Фамилия" --role admin'
# вывод: OK created: ... / PASSWORD: <сгенерированный>

# Сбросить пароль (генерируется новый)
ssh ceo24 'docker exec $(docker ps -qf name=backend) python scripts/manage_users.py reset-password \
    --email user@example.ru'

# Сбросить пароль с заданным значением
ssh ceo24 'docker exec $(docker ps -qf name=backend) python scripts/manage_users.py reset-password \
    --email user@example.ru --password "Мой_Новый_Пароль123"'

# Сменить роль
ssh ceo24 'docker exec $(docker ps -qf name=backend) python scripts/manage_users.py set-role \
    --email user@example.ru --role manager'

# Деактивировать (login перестанет работать, данные сохранятся)
ssh ceo24 'docker exec $(docker ps -qf name=backend) python scripts/manage_users.py deactivate \
    --email user@example.ru'
```

После любых изменений — записать новый пароль в `~/.config/ceo24/credentials` (chmod 600).

### Через API (если admin может залогиниться)

```bash
TOKEN=$(curl -sS -X POST https://ceo.pass24pro.ru/api/v1/auth/login \
    -H "Content-Type: application/x-www-form-urlencoded" \
    --data-urlencode "username=admin@example.ru" \
    --data-urlencode "password=PASSWORD" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Список
curl -sS https://ceo.pass24pro.ru/api/v1/users -H "Authorization: Bearer $TOKEN"

# Сменить свой пароль
curl -sS -X POST https://ceo.pass24pro.ru/api/v1/auth/change-password \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"current_password":"OLD","new_password":"NEW123!@"}'
```

## Мониторинг

- **Uptime:** UptimeRobot — настройка `https://uptimerobot.com` (HTTP-checks на `/` и `/docs` каждые 5 мин, Telegram-алерт). См. `agent_docs/guides/uptime-monitor-setup.md` (TODO).
- **Внутренние healthchecks:** Docker сам перезапускает `backend` и `frontend` если они unhealthy.
- **Zabbix-agent** (10050) — мониторит хост (CPU, диск, память) на стороне Timeweb. **Не видит** контейнеры — поэтому нужен внешний uptime-check.

## Ключевые параметры

| Параметр | Значение |
|---|---|
| Restart policy | `unless-stopped` для всех 3 сервисов |
| Healthcheck backend | `GET /health` каждые 30 сек, start_period 20 сек |
| Healthcheck frontend | `wget /` каждые 30 сек |
| Healthcheck db | `pg_isready` каждые 10 сек |
| Лог-ротация | 10 MB × 3 файла на каждый сервис |
| Swap | 2 GB, swappiness=10 (в /etc/sysctl.conf и /etc/fstab) |
| Бэкап локальный | ежедневно в 03:00 UTC, ретеншн 14 дней |
| Бэкап offsite S3 | в том же запуске после локального дампа, ретеншн 30 дней |
| Pull на ноут | ежедневно в 05:00 локального через launchd |

## Где что лежит на сервере

```
/root/pass24-ceo-dashbord/    # git checkout, docker-compose.yml
/srv/ceo24/pgdata/             # PostgreSQL data (bind mount в контейнер db)
/srv/ceo24/backups/            # ежедневные дампы (.dump.gz)
/usr/local/bin/ceo24-backup.sh # скрипт бэкапа (локальный + S3 offsite)
/etc/cron.d/ceo24-backup       # cron-задача бэкапа
/etc/cron.d/ceo24-alerts       # cron-задача генерации алертов (P3.4) — 09:00 МСК ежедневно
/etc/ceo24/backup-s3.env       # ключи TimeWeb S3 (chmod 600)
/var/log/ceo24-backup.log      # лог бэкапов (строки OK local / OK s3)
/var/log/ceo24-alerts.log      # лог запусков run_alerts (alerts created: total=N ...)
/swapfile                       # 2 GB swap
```

## Алерты (P3.4)

Запускаются раз в день в 09:00 МСК через `/etc/cron.d/ceo24-alerts`:
- `NON_PAYMENT` — просрочка >=30/60/90 дней (severity INFO/WARNING/CRITICAL)
- `UNASSIGNED_CLIENT` — клиент в реестре >14 дней без manager_id
- `CHURN_RISK` — ACTIVE без аллокаций 2 месяца подряд

Идемпотентны: повторно открытый алерт того же type+org не создаётся.
Ручной dry-run: `cd /root/pass24-ceo-dashbord && docker compose exec -T backend python -m scripts.run_alerts`.
Логи генерации: `tail -50 /var/log/ceo24-alerts.log`.
Просмотр открытых алертов: UI `/alerts` или плитка «Требуют внимания» на Dashboard.

## Audit log админских действий

Таблица `audit_log` — все действия admin'ов (`user.create`, `user.reset_password`,
`organization.write_off_debt`) пишутся через `app.services.audit_service.write_audit`.
Снапшот `actor_email` сохраняется на случай удаления пользователя.
Просмотр за период: `docker exec pass24-ceo-dashbord-db-1 psql -U ceo24 -d ceo24
-c "SELECT created_at, action, actor_email, details FROM audit_log
WHERE created_at > now() - interval '7 days' ORDER BY created_at DESC;"`
