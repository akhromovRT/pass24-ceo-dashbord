# Runbook — CEO24 production (85.239.51.34)

Операционные процедуры для восстановления и эксплуатации production-сервиса.

## Доступ

| Что | Как |
|---|---|
| SSH | `ssh ceo24` (alias в `~/.ssh/config`) |
| SSH-ключ | `~/.ssh/ceo24_ed25519` |
| UI | http://85.239.51.34 |
| Логин | `admin@onvi-service.ru` (пароль — `~/.config/ceo24/credentials`, chmod 600, не в репо) |
| Compose-директория | `/root/pass24-ceo-dashbord/` |
| Backups директория на сервере | `/srv/ceo24/backups/` |
| Backups локально (зеркало) | `~/Backups/ceo24/` (pull в 05:00 через launchd) |
| Логи бэкапа на сервере | `/var/log/ceo24-backup.log` |

## Сайт не открывается — что делать

### 1. Базовая диагностика
```bash
ping 85.239.51.34                              # хост жив?
curl -sI http://85.239.51.34/                  # nginx отвечает?
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
curl -sI http://85.239.51.34/
```

Если на ноуте более свежий бэкап (например, серверный диск убит):

```bash
scp ~/Backups/ceo24/ceo24-<latest>.dump.gz ceo24:/tmp/
ssh ceo24 'gunzip < /tmp/ceo24-<latest>.dump.gz | docker exec -i $(docker ps -qf name=db) pg_restore -U ceo24 -d ceo24 --clean --if-exists --no-owner'
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

## Состояние подсистем (квик-чек)

```bash
ssh ceo24 'docker compose -f /root/pass24-ceo-dashbord/docker-compose.yml ps; \
  echo "---disk---"; df -h /; \
  echo "---mem---"; free -m; \
  echo "---backups---"; ls -lh /srv/ceo24/backups/ | tail -5; \
  echo "---last cron log---"; tail -5 /var/log/ceo24-backup.log 2>/dev/null'
```

## Сброс пароля админа

> **Внимание:** требует осторожности. Выполнять только при явной необходимости (например, забыт пароль).

```bash
# Сгенерировать новый пароль и хеш локально
PW=$(python3 -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters+string.digits+'-_.') for _ in range(24)))")
HASH=$(cd ~/Library/Mobile\ Documents/com~apple~CloudDocs/Cursor/@work-projects/pass24-ceo-dashbord/backend && .venv/bin/python -c "import bcrypt; print(bcrypt.hashpw('$PW'.encode(), bcrypt.gensalt()).decode())")

# Записать новый пароль в локальный credentials-файл
echo "ADMIN_PASSWORD=$PW" >> ~/.config/ceo24/credentials

# Применить в БД (хеш в одинарных кавычках, чтобы bash не интерпретировал спецсимволы bcrypt)
ssh ceo24 "docker exec -i \$(docker ps -qf name=db) psql -U ceo24 -d ceo24 -c \"UPDATE users SET hashed_password='$HASH' WHERE email='admin@onvi-service.ru';\""
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
| Бэкап | ежедневно в 03:00 UTC, ретеншн 14 дней |
| Pull на ноут | ежедневно в 05:00 локального через launchd |

## Где что лежит на сервере

```
/root/pass24-ceo-dashbord/    # git checkout, docker-compose.yml
/srv/ceo24/pgdata/             # PostgreSQL data (bind mount в контейнер db)
/srv/ceo24/backups/            # ежедневные дампы (.dump.gz)
/usr/local/bin/ceo24-backup.sh # скрипт бэкапа
/etc/cron.d/ceo24-backup       # cron-задача
/var/log/ceo24-backup.log      # лог бэкапов
/swapfile                       # 2 GB swap
```
