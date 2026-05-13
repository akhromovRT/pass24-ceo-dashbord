# CEO24 — Recovery & Reliability Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** восстановить упавший production-сервис на `85.239.51.34`, сделать инфраструктуру устойчивой к перезагрузкам/падениям, перевести PostgreSQL на персистентное хранилище в том же контейнере с автоматическим бэкапом — без перевода на managed-БД и без домена.

**Architecture:** Docker Compose стек (postgres + backend + frontend/nginx) на одном VPS Timeweb. PostgreSQL хранит данные в bind-mount директории на хосте `/srv/ceo24/pgdata/` — переживает пересоздание контейнера. Доступ к админке по HTTP через IP. Бэкапы — cron `pg_dump` ежедневно, хранение локально + копия в Yandex Object Storage / iCloud.

**Tech Stack:** Docker Compose, PostgreSQL 16-alpine, FastAPI, Vue/Nginx, systemd-таймеры или cron, UptimeRobot (free) для алертов.

**Решения, зафиксированные пользователем 2026-05-13:**
- Доступ остаётся по IP, домен не подключаем
- БД — на том же сервере, в контейнере (managed PostgreSQL не используем)
- SSH-ключ загрузим на сервер (root-пароль предоставит пользователь при необходимости)
- Этапы P0 → P1 → P2 идём последовательно; P3 уточним отдельно

---

## Этапы

| Этап | Цель | Срок |
|---|---|---|
| **P0** | Реанимация: сайт открывается, данные сохранены в дамп | 1–2 ч |
| **P1** | Надёжность: автоперезапуск, healthchecks, мониторинг, логи, runbook | 1 день |
| **P2** | Персистентная БД на хосте + автобэкап | 1 день |
| **P3** | Развитие функциональности (сверка платежей, прогноз MRR, роли, алерты) | план уточняется |

---

## Этап P0 — Реанимация

**DoD этапа:** `curl http://85.239.51.34` возвращает HTTP 200 • `SELECT COUNT(*) FROM organizations` ≥ 268 • локально сохранён `ceo24-YYYY-MM-DD.sql.gz`.

### Task P0.1: Настроить SSH-доступ к VPS

**Files:**
- Modify: `~/.ssh/config`
- Create: `~/.ssh/ceo24_ed25519` (через ssh-keygen)

- [ ] **Step 1: Сгенерировать выделенный SSH-ключ для CEO24**

```bash
ssh-keygen -t ed25519 -f ~/.ssh/ceo24_ed25519 -C "ceo24-vps-akhromov" -N ""
```

Ожидаемо: создаются `~/.ssh/ceo24_ed25519` и `~/.ssh/ceo24_ed25519.pub`.

- [ ] **Step 2: Запросить у пользователя root-пароль и установить ключ на сервер**

Запросить пароль в чате, затем:

```bash
ssh-copy-id -i ~/.ssh/ceo24_ed25519.pub root@85.239.51.34
```

Альтернатива (если `ssh-copy-id` не сработал):

```bash
cat ~/.ssh/ceo24_ed25519.pub | ssh root@85.239.51.34 'mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
```

- [ ] **Step 3: Добавить запись в `~/.ssh/config`**

Дописать в конец файла:

```
Host ceo24
  HostName 85.239.51.34
  User root
  IdentityFile ~/.ssh/ceo24_ed25519
  IdentitiesOnly yes
```

- [ ] **Step 4: Проверить, что ключ работает без пароля**

```bash
ssh ceo24 'hostname && uname -a'
```

Ожидаемо: имя хоста и `Linux ... GNU/Linux` без запроса пароля.

- [ ] **Step 5: Commit**

Только конфиг (ключ не коммитим). В репозиторий — добавить запись в runbook позже (Task P1.5).

---

### Task P0.2: Диагностика состояния сервера

**Files:**
- Read-only

- [ ] **Step 1: Снять снимок состояния**

```bash
ssh ceo24 'echo "=== docker ===" && docker ps -a && echo "=== compose ===" && docker compose ls 2>/dev/null && echo "=== disk ===" && df -h && echo "=== mem ===" && free -m && echo "=== uptime ===" && uptime && echo "=== kernel ===" && dmesg | tail -20'
```

Ожидаемо: видим состояние всех контейнеров (Exited / Up / удалены), наличие свободного места, последние события ядра.

- [ ] **Step 2: Найти рабочую директорию compose-проекта**

```bash
ssh ceo24 'find / -maxdepth 5 -name docker-compose.yml -not -path "*/var/lib/*" 2>/dev/null'
```

Ожидаемо: путь типа `/root/ceo24/docker-compose.yml` или `/srv/ceo24/docker-compose.yml`.

- [ ] **Step 3: Зафиксировать путь в переменной для следующих шагов**

Записать путь как `CEO24_DIR` для дальнейших команд. Например `/root/pass24-ceo-dashbord`.

- [ ] **Step 4: Определить тип Timeweb-инстанса**

```bash
ssh ceo24 'cat /etc/os-release && which docker && docker info | grep -i "Storage Driver\|Server Version"'
```

Если есть полноценный Docker engine и `apt`/`yum` работают — это обычный VPS, можно использовать `volumes` (P2 пройдёт легко). Если это managed Apps-окружение — будут ограничения, фиксируем для P2.

---

### Task P0.3: Снять дамп БД ДО любых изменений

> **Критично:** делаем дамп даже если контейнер `Exited` — данные могут быть живы в overlay-слое. До рестарта.

**Files:**
- Create: `~/Backups/ceo24/ceo24-pre-recovery-YYYY-MM-DD.sql.gz` (локально на ноуте)

- [ ] **Step 1: Создать локальную папку для бэкапов**

```bash
mkdir -p ~/Backups/ceo24
```

- [ ] **Step 2: Запустить ТОЛЬКО контейнер БД (если он Exited)**

Если `docker ps -a` показал `db` в статусе `Exited`:

```bash
ssh ceo24 'cd $CEO24_DIR && docker compose start db'
sleep 5
ssh ceo24 'docker compose -f $CEO24_DIR/docker-compose.yml exec db pg_isready -U ceo24'
```

Ожидаемо: `accepting connections`.

Если контейнер `db` уже удалён — переходим к Task P0.5 (восстановление с нуля).

- [ ] **Step 3: Снять дамп через stream на ноутбук**

```bash
DATE=$(date +%F)
ssh ceo24 "docker exec \$(docker ps -qf name=db) pg_dump -U ceo24 -Fc ceo24" > ~/Backups/ceo24/ceo24-pre-recovery-$DATE.dump
ls -lh ~/Backups/ceo24/
```

Ожидаемо: файл ≥ 100 KB (для 268 организаций и снапшотов — ожидаемо 1–5 MB).

- [ ] **Step 4: Проверить целостность дампа**

```bash
pg_restore --list ~/Backups/ceo24/ceo24-pre-recovery-$DATE.dump | head -30
```

Ожидаемо: видим записи `TABLE DATA public organizations`, `TABLE DATA public contracts` и т.д.

Если `pg_restore` не установлен на mac, установить: `brew install libpq && brew link --force libpq`.

- [ ] **Step 5: Зафиксировать факт бэкапа**

Записать в чат: размер файла, количество таблиц. Это станет точкой отката, если P2 пойдёт неудачно.

---

### Task P0.4: Поднять стек и проверить работу

**Files:**
- Read-only (изменения compose-файла будут в P1)

- [ ] **Step 1: Запустить полный стек**

```bash
ssh ceo24 'cd $CEO24_DIR && docker compose up -d'
sleep 10
ssh ceo24 'cd $CEO24_DIR && docker compose ps'
```

Ожидаемо: все три сервиса в статусе `Up` или `Up (healthy)`.

- [ ] **Step 2: Проверить логи backend**

```bash
ssh ceo24 'cd $CEO24_DIR && docker compose logs --tail=30 backend'
```

Ожидаемо: `Uvicorn running on http://0.0.0.0:8000`. Если есть ошибки подключения к БД — проверить переменные окружения.

- [ ] **Step 3: Smoke-test с локальной машины**

```bash
curl -sS -o /dev/null -w "HTTP=%{http_code} TIME=%{time_total}s\n" http://85.239.51.34/
curl -sS -o /dev/null -w "API=%{http_code}\n" http://85.239.51.34/docs
curl -sS http://85.239.51.34/api/v1/dashboard/summary -H "Authorization: Bearer ..." | head -c 200
```

Ожидаемо: HTTP 200 на `/`, 200 на `/docs`. На `/api` без токена — 401, это нормально.

- [ ] **Step 4: Проверить данные через psql**

```bash
ssh ceo24 'docker exec $(docker ps -qf name=db) psql -U ceo24 -d ceo24 -c "SELECT COUNT(*) AS orgs FROM organizations; SELECT COUNT(*) AS contracts FROM contracts; SELECT COUNT(*) AS docs FROM documents;"'
```

Ожидаемо:
- orgs ≈ 268
- contracts ≈ 376
- docs ≈ 3814

Если цифры не совпадают — данные пострадали, использовать дамп из P0.3 как референс.

- [ ] **Step 5: Проверить логин через UI**

Открыть http://85.239.51.34 в браузере, войти `admin / Admin123!`, открыть Дашборд — должны быть KPI и графики.

- [ ] **Step 6: Commit (не нужен — изменений в репо нет)**

Этап P0 завершён, когда: сайт открыт в браузере, данные на месте, дамп сохранён локально.

---

### Task P0.5: Аварийный путь — восстановление при потере данных

> Выполнять **только если** в Task P0.4 Step 4 счётчики = 0 или контейнер `db` был удалён.

**Files:**
- Использовать: `~/Downloads/_Spreadsheets/Задолженность покупателей за 2025 г. ООО  ОНВИ СЕРВИС.xls`
- Использовать: `~/Library/Mobile Documents/com~apple~CloudDocs/ClaudeCode/Аналитика поступлений/Аналитика_поступлений_2025_2026.xlsx`

- [ ] **Step 1: Применить миграции на пустую БД**

```bash
ssh ceo24 'cd $CEO24_DIR && docker compose exec backend alembic upgrade head'
```

Ожидаемо: `Running upgrade ... -> 2347cbabe6c7, initial_schema`.

- [ ] **Step 2: Создать seed-пользователя**

```bash
ssh ceo24 'cd $CEO24_DIR && docker compose exec backend python scripts/seed_admin.py'
```

Ожидаемо: создан admin / Admin123!.

- [ ] **Step 3: Загрузить отчёт «Задолженность покупателей» через UI**

Зайти на http://85.239.51.34, страница «Импорт», drag-and-drop `.xls`.

Ожидаемо: после импорта — 268 orgs, 376 contracts, 3814 documents.

- [ ] **Step 4: Запустить seed-скрипт для аналитики**

```bash
scp "/Users/akhromov/Library/Mobile Documents/com~apple~CloudDocs/ClaudeCode/Аналитика поступлений/Аналитика_поступлений_2025_2026.xlsx" ceo24:/tmp/analytics.xlsx
ssh ceo24 'cd $CEO24_DIR && docker compose exec backend python scripts/seed_data.py /tmp/analytics.xlsx'
```

Ожидаемо: ~176 orgs обновлено, ~182 contracts, ~3428 snapshots.

- [ ] **Step 5: Сверить с эталонными цифрами**

MRR ≈ 4 483 322 ₽ на дашборде. Если расходится — пометить как известное расхождение и продолжать.

---

## Этап P1 — Надёжность инфраструктуры

**DoD этапа:** перезагрузка VPS → стек поднимается сам за < 60 сек • в проекте есть `agent_docs/guides/runbook.md` • настроен внешний uptime-check • логи ротируются.

### Task P1.1: Добавить restart policy и healthchecks в docker-compose

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Открыть текущий docker-compose.yml**

Файл уже прочитан в начале сессии (см. P0 диагностику). Текущее состояние: 3 сервиса без restart/healthcheck (кроме db).

- [ ] **Step 2: Применить изменения**

Полностью заменить `docker-compose.yml` на:

```yaml
services:
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: ceo24
      POSTGRES_PASSWORD: ceo24
      POSTGRES_DB: ceo24
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ceo24"]
      interval: 10s
      timeout: 3s
      retries: 5
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  backend:
    build: ./backend
    restart: unless-stopped
    expose:
      - "8000"
    environment:
      DATABASE_URL: postgresql+psycopg://ceo24:ceo24@db:5432/ceo24
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health',timeout=3).status==200 else 1)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  frontend:
    build: ./frontend
    restart: unless-stopped
    ports:
      - "80:80"
    depends_on:
      - backend
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost/"]
      interval: 30s
      timeout: 5s
      retries: 3
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

- [ ] **Step 3: Скопировать на сервер и применить**

```bash
scp docker-compose.yml ceo24:$CEO24_DIR/docker-compose.yml
ssh ceo24 "cd \$CEO24_DIR && docker compose up -d"
```

Ожидаемо: `Recreating ...` для всех трёх сервисов. Через ~30 сек все `Up (healthy)`.

- [ ] **Step 4: Проверить, что данные на месте**

```bash
ssh ceo24 'docker exec $(docker ps -qf name=db) psql -U ceo24 -d ceo24 -c "SELECT COUNT(*) FROM organizations;"'
```

Ожидаемо: то же число, что в P0.4. Если 0 — **СТОП**, восстановиться из дампа P0.3, пересмотреть P2.

> На этом этапе данные ещё в overlay-слое контейнера — каждый `docker compose up` с пересборкой `db` теряет их. Это будет исправлено в P2.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml
git commit -m "infra: add restart policies, healthchecks, log rotation"
```

---

### Task P1.2: Smoke-тест автовосстановления

**Files:**
- Read-only

- [ ] **Step 1: Симулировать падение backend**

```bash
ssh ceo24 'docker kill $(docker ps -qf name=backend)'
sleep 20
ssh ceo24 'docker ps -f name=backend'
```

Ожидаемо: контейнер снова `Up`, аптайм меньше минуты, статус `(healthy)` после ~30 сек.

- [ ] **Step 2: Симулировать ребут хоста**

```bash
ssh ceo24 'reboot'
sleep 60
ssh ceo24 'docker ps'
```

Ожидаемо: все три контейнера снова `Up`. Если нет — Docker daemon не настроен на автозапуск:

```bash
ssh ceo24 'systemctl enable docker && systemctl start docker'
```

- [ ] **Step 3: Финальный curl-чек**

```bash
curl -sS -o /dev/null -w "HTTP=%{http_code}\n" http://85.239.51.34/
```

Ожидаемо: HTTP 200.

---

### Task P1.3: Настроить внешний мониторинг (UptimeRobot)

**Files:**
- Действия в браузере, конфигурация на стороне UptimeRobot

- [ ] **Step 1: Зарегистрировать аккаунт UptimeRobot (free tier)**

Открыть https://uptimerobot.com, регистрация бесплатная, до 50 мониторов с интервалом 5 мин.

- [ ] **Step 2: Создать монитор**

- Type: HTTP(s)
- URL: `http://85.239.51.34/`
- Name: `CEO24 production`
- Interval: 5 minutes

- [ ] **Step 3: Создать второй монитор на API**

- URL: `http://85.239.51.34/docs` (страница Swagger, статически отдаётся FastAPI)
- Name: `CEO24 API`

- [ ] **Step 4: Подключить Telegram-уведомления**

В разделе «My Settings → Add Alert Contact» подключить Telegram через бота @UptimeRobotBot.

- [ ] **Step 5: Проверить алерт**

Временно остановить `frontend`:

```bash
ssh ceo24 'docker stop $(docker ps -qf name=frontend)'
```

Ожидаемо: через ~5 мин — уведомление в Telegram «CEO24 production is DOWN». Затем поднять обратно: `docker start ...`.

---

### Task P1.4: Лог-ротация и базовый аудит

**Files:**
- Modify (already done in P1.1): `docker-compose.yml` — `logging` блок добавлен
- Verify: системная docker daemon-config

- [ ] **Step 1: Проверить, что лимит логов работает**

```bash
ssh ceo24 'du -sh /var/lib/docker/containers/*/  2>/dev/null | sort -h | tail -5'
```

Ожидаемо: ни одна папка контейнера > 50 MB (3 файла × 10 MB лимит).

- [ ] **Step 2: Опционально — глобальные настройки Docker daemon**

```bash
ssh ceo24 'cat > /etc/docker/daemon.json <<EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF
systemctl reload docker'
```

(Это покрывает любые будущие контейнеры без необходимости править каждый compose.)

---

### Task P1.5: Runbook восстановления

**Files:**
- Create: `agent_docs/guides/runbook.md`

- [ ] **Step 1: Создать файл runbook.md**

Содержание:

```markdown
# Runbook — CEO24 production (85.239.51.34)

## Доступ

- SSH: `ssh ceo24` (alias из `~/.ssh/config`)
- Ключ: `~/.ssh/ceo24_ed25519`
- UI: http://85.239.51.34 (admin / Admin123!)
- Рабочая директория на сервере: `$CEO24_DIR` (см. `~/.ssh/config` Note или историю)

## Сайт не открывается — что делать

1. **Проверить хост:** `ping 85.239.51.34` — если не пингуется, проблема на стороне Timeweb, идти в их панель.
2. **Подключиться:** `ssh ceo24`
3. **Состояние контейнеров:** `docker ps -a`
   - Все `Up (healthy)` — проблема в приложении, смотреть логи
   - Какой-то `Exited` — `docker compose up -d` поднимет
   - Контейнеры отсутствуют — авария, идти в раздел «Полное восстановление»
4. **Диск:** `df -h` — если 100 %, чистить логи `docker system prune -a`
5. **Память:** `free -m` — если OOM, перезагрузка `reboot`
6. **Логи приложения:** `docker compose logs --tail=100 backend`

## Полное восстановление из бэкапа

1. `ssh ceo24 'cd $CEO24_DIR && docker compose up -d db'`
2. Дождаться `pg_isready`
3. Перезалить из последнего дампа:
   ```bash
   gunzip < ~/Backups/ceo24/ceo24-latest.sql.gz | ssh ceo24 'docker exec -i $(docker ps -qf name=db) psql -U ceo24 ceo24'
   ```
4. `docker compose up -d`

## Ежедневный бэкап

Запускается cron на сервере (см. `/etc/cron.d/ceo24-backup`).
Локальная копия — на ноуте в `~/Backups/ceo24/` через rsync (опционально).

## Куда смотреть

- Uptime: https://uptimerobot.com (аккаунт akhromovrt@gmail.com)
- Логи: `docker compose logs -f` (по сервису или все)
- БД: `docker exec -it $(docker ps -qf name=db) psql -U ceo24 ceo24`
```

- [ ] **Step 2: Обновить index.md**

В `agent_docs/index.md` в раздел «Правила и гайды» добавить:

```markdown
- `agent_docs/guides/runbook.md` — операционный runbook production-сервера.
```

- [ ] **Step 3: Commit**

```bash
git add agent_docs/guides/runbook.md agent_docs/index.md
git commit -m "docs: add production runbook"
```

---

## Этап P2 — Персистентная БД на хосте + автобэкап

**DoD этапа:** `docker compose down && docker compose up -d` не теряет данные • ежедневный дамп лежит на сервере и копируется в облако • один успешный test-restore выполнен • ADR обновлён.

### Task P2.1: Выбрать стратегию persistence по результатам P0.2

**Files:**
- Modify: `agent_docs/adr.md` — добавить ADR-010

- [ ] **Step 1: Применить решение по результату диагностики P0.2 Step 4**

| Тип инстанса | Стратегия |
|---|---|
| Обычный VPS (Docker engine + apt) | Bind mount `/srv/ceo24/pgdata:/var/lib/postgresql/data` |
| Managed Apps (если volumes реально запрещены) | Перейти на обычный VPS (отдельный тикет, ADR-обновление) |

Зафиксировать решение текстом — в чате и в новом ADR-010.

- [ ] **Step 2: Создать ADR-010**

Дописать в `agent_docs/adr.md`:

```markdown
### ADR-010: PostgreSQL persistence — bind mount на хосте

**Дата:** 2026-05-13
**Статус:** Принято
**Контекст:** ADR-007 (без volumes) был принят под managed Timeweb. После инцидента 2026-05-13 — переоценка: managed-БД отклонена (бюджет), решено хранить данные на этом же VPS.
**Решение:** PostgreSQL хранит данные в bind mount `/srv/ceo24/pgdata` на хосте. Каталог создаётся вне рабочей директории проекта, что делает данные независимыми от `git pull` / пересоздания compose. Права: `999:999` (postgres uid в alpine-образе).
**Последствия:** Пересоздание контейнера `db` не теряет данные. Бэкап — отдельный механизм (cron pg_dump, см. Task P2.3). ADR-007 помечен superseded by ADR-010.
```

Изменить шапку ADR-007:

```markdown
### ADR-007: Docker без named volumes (Timeweb)

**Дата:** 2026-03-07
**Статус:** Superseded by ADR-010
```

- [ ] **Step 3: Commit**

```bash
git add agent_docs/adr.md
git commit -m "docs: ADR-010 persistent postgres via bind mount, supersede ADR-007"
```

---

### Task P2.2: Перевести БД на bind mount без потери данных

**Files:**
- Modify: `docker-compose.yml`
- Server: создать `/srv/ceo24/pgdata`

- [ ] **Step 1: Свежий дамп прямо перед миграцией**

```bash
DATE=$(date +%F-%H%M)
ssh ceo24 "docker exec \$(docker ps -qf name=db) pg_dump -U ceo24 -Fc ceo24" > ~/Backups/ceo24/ceo24-before-p2-$DATE.dump
ls -lh ~/Backups/ceo24/ceo24-before-p2-$DATE.dump
```

- [ ] **Step 2: Создать директорию на хосте**

```bash
ssh ceo24 'mkdir -p /srv/ceo24/pgdata && chown -R 999:999 /srv/ceo24/pgdata && chmod 700 /srv/ceo24/pgdata'
```

- [ ] **Step 3: Обновить docker-compose.yml — добавить volume для db**

Изменить блок `db:` в `docker-compose.yml`:

```yaml
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: ceo24
      POSTGRES_PASSWORD: ceo24
      POSTGRES_DB: ceo24
    ports:
      - "5432:5432"
    volumes:
      - /srv/ceo24/pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ceo24"]
      interval: 10s
      timeout: 3s
      retries: 5
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

- [ ] **Step 4: Остановить стек, скопировать compose, поднять заново**

```bash
ssh ceo24 'cd $CEO24_DIR && docker compose down'
scp docker-compose.yml ceo24:$CEO24_DIR/
ssh ceo24 'cd $CEO24_DIR && docker compose up -d db'
sleep 10
ssh ceo24 'docker exec $(docker ps -qf name=db) pg_isready -U ceo24'
```

Ожидаемо: новый контейнер `db`, инициализированная пустая БД на bind mount.

- [ ] **Step 5: Залить дамп**

```bash
cat ~/Backups/ceo24/ceo24-before-p2-$DATE.dump | ssh ceo24 'docker exec -i $(docker ps -qf name=db) pg_restore -U ceo24 -d ceo24 --clean --if-exists --no-owner'
```

Ожидаемо: процесс ~30 сек, в конце 0 errors.

- [ ] **Step 6: Проверить данные**

```bash
ssh ceo24 'docker exec $(docker ps -qf name=db) psql -U ceo24 -d ceo24 -c "SELECT COUNT(*) FROM organizations; SELECT COUNT(*) FROM contracts; SELECT COUNT(*) FROM documents; SELECT COUNT(*) FROM monthly_snapshots;"'
```

Ожидаемо: те же числа, что были до миграции.

- [ ] **Step 7: Поднять остальные сервисы**

```bash
ssh ceo24 'cd $CEO24_DIR && docker compose up -d'
sleep 15
curl -sS -o /dev/null -w "HTTP=%{http_code}\n" http://85.239.51.34/
```

Ожидаемо: HTTP 200.

- [ ] **Step 8: Тест persistence**

```bash
ssh ceo24 'cd $CEO24_DIR && docker compose rm -fs db && docker compose up -d db'
sleep 15
ssh ceo24 'docker exec $(docker ps -qf name=db) psql -U ceo24 -d ceo24 -c "SELECT COUNT(*) FROM organizations;"'
```

Ожидаемо: данные на месте после полного пересоздания контейнера. **Это и есть проверка, что ADR-010 работает.**

- [ ] **Step 9: Commit**

```bash
git add docker-compose.yml
git commit -m "infra: persist postgres on host bind mount /srv/ceo24/pgdata"
```

---

### Task P2.3: Ежедневный автобэкап (cron на сервере)

**Files:**
- Create on server: `/usr/local/bin/ceo24-backup.sh`
- Create on server: `/etc/cron.d/ceo24-backup`
- Create on server: `/srv/ceo24/backups/` directory

- [ ] **Step 1: Создать каталог бэкапов**

```bash
ssh ceo24 'mkdir -p /srv/ceo24/backups && chmod 700 /srv/ceo24/backups'
```

- [ ] **Step 2: Скрипт бэкапа**

```bash
ssh ceo24 'cat > /usr/local/bin/ceo24-backup.sh <<'\''EOF'\''
#!/bin/bash
set -euo pipefail
BACKUP_DIR=/srv/ceo24/backups
RETAIN_DAYS=14
DATE=$(date +%F-%H%M)
FILE=$BACKUP_DIR/ceo24-$DATE.dump.gz

CONTAINER=$(docker ps -qf name=db)
if [ -z "$CONTAINER" ]; then
  echo "ERROR: db container not running" >&2
  exit 1
fi

docker exec "$CONTAINER" pg_dump -U ceo24 -Fc ceo24 | gzip > "$FILE"
SIZE=$(stat -c%s "$FILE")
if [ "$SIZE" -lt 10000 ]; then
  echo "ERROR: backup suspiciously small ($SIZE bytes)" >&2
  rm "$FILE"
  exit 2
fi

find "$BACKUP_DIR" -name "ceo24-*.dump.gz" -mtime +$RETAIN_DAYS -delete
echo "OK: $FILE ($SIZE bytes)"
EOF
chmod +x /usr/local/bin/ceo24-backup.sh'
```

- [ ] **Step 3: Тестовый прогон**

```bash
ssh ceo24 '/usr/local/bin/ceo24-backup.sh'
ssh ceo24 'ls -lh /srv/ceo24/backups/'
```

Ожидаемо: `OK: /srv/ceo24/backups/ceo24-...dump.gz (N bytes)`, размер 100 KB – 5 MB.

- [ ] **Step 4: Cron-задача (03:00 ежедневно)**

```bash
ssh ceo24 'cat > /etc/cron.d/ceo24-backup <<EOF
0 3 * * * root /usr/local/bin/ceo24-backup.sh >> /var/log/ceo24-backup.log 2>&1
EOF'
ssh ceo24 'systemctl reload cron 2>/dev/null || service cron reload'
```

- [ ] **Step 5: Проверить cron**

```bash
ssh ceo24 'cat /etc/cron.d/ceo24-backup && ls /etc/cron.d/'
```

Ожидаемо: файл создан, синтаксис корректный.

---

### Task P2.4: Зеркалирование бэкапов на ноут (pull-модель)

> **Решение:** бэкап-копия живёт на стороне ноутбука (iCloud-папка), pull раз в сутки. Это проще, чем настраивать push в Object Storage, и достаточно для текущего объёма.

**Files:**
- Create: `~/bin/ceo24-pull-backup.sh`
- Create: `~/Library/LaunchAgents/com.akhromov.ceo24-backup-pull.plist`

- [ ] **Step 1: Скрипт pull-а**

```bash
mkdir -p ~/bin
cat > ~/bin/ceo24-pull-backup.sh <<'EOF'
#!/bin/bash
set -euo pipefail
LOCAL=~/Backups/ceo24
mkdir -p "$LOCAL"
rsync -avz --delete ceo24:/srv/ceo24/backups/ "$LOCAL/"
echo "$(date) pulled $(ls "$LOCAL" | wc -l) files" >> "$LOCAL/.pull.log"
EOF
chmod +x ~/bin/ceo24-pull-backup.sh
```

- [ ] **Step 2: launchd-агент на ноуте — pull раз в сутки в 05:00**

```bash
cat > ~/Library/LaunchAgents/com.akhromov.ceo24-backup-pull.plist <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.akhromov.ceo24-backup-pull</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/akhromov/bin/ceo24-pull-backup.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>5</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key><string>/Users/akhromov/Library/Logs/ceo24-backup-pull.log</string>
  <key>StandardErrorPath</key><string>/Users/akhromov/Library/Logs/ceo24-backup-pull.log</string>
</dict>
</plist>
EOF
launchctl load ~/Library/LaunchAgents/com.akhromov.ceo24-backup-pull.plist
```

- [ ] **Step 3: Тестовый прогон**

```bash
~/bin/ceo24-pull-backup.sh
ls -lh ~/Backups/ceo24/
```

Ожидаемо: бэкап из P2.3 Step 3 уже скопирован на ноут.

---

### Task P2.5: Тест восстановления (DR-drill)

> **Бэкап, который ни разу не восстанавливали, статистически не существует.** Делаем один полный цикл restore в изолированную БД.

**Files:**
- Read-only

- [ ] **Step 1: Поднять локально временный postgres**

```bash
docker run -d --name ceo24-restore-test -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:16-alpine
sleep 5
```

- [ ] **Step 2: Создать пустую БД**

```bash
docker exec ceo24-restore-test psql -U postgres -c "CREATE DATABASE ceo24_restore_test;"
```

- [ ] **Step 3: Восстановить из последнего бэкапа**

```bash
LATEST=$(ls -t ~/Backups/ceo24/ceo24-*.dump.gz | head -1)
gunzip < "$LATEST" | docker exec -i ceo24-restore-test pg_restore -U postgres -d ceo24_restore_test --no-owner
```

- [ ] **Step 4: Сверить данные**

```bash
docker exec ceo24-restore-test psql -U postgres -d ceo24_restore_test -c "SELECT COUNT(*) FROM organizations; SELECT COUNT(*) FROM contracts;"
```

Ожидаемо: те же числа, что в production.

- [ ] **Step 5: Удалить временный контейнер**

```bash
docker rm -f ceo24-restore-test
```

- [ ] **Step 6: Зафиксировать в development-history**

Добавить запись о P0-P2 в `agent_docs/development-history.md`. Старую запись «2026-03-04 — Инициализация проекта» — перенести в `development-history-archive.md` (правило: 10 записей в активной истории).

---

## Этап P3 — Развитие функциональности (план уточняется)

> Этот этап декомпозируется в отдельный план после успешного завершения P2. Здесь — только список, согласованный по приоритету. Детали — позже.

### Кандидаты (в порядке value/effort)

1. **P3.1 — Сверка платежей с банком.** Парсер `bank_statement.py` готов и оттестирован, нужно: тип источника в `POST /import/upload`, сервис match-инга (ИНН + сумма + период), UI-вкладка «Сверка», алерт «платёж без документа». ~1 неделя.
2. **P3.2 — Прогноз MRR.** На дашборд — линия прогноза вперёд на 12 мес с учётом churn. ~3-5 дней.
3. **P3.3 — Реальные пользователи и роли.** Создать `manager` / `viewer`, привязать `manager_id` через UI, фильтр «мои клиенты». ~2 дня.
4. **P3.4 — Алерты по расписанию.** Cron-service для 9 типов алертов из `alert.py` (просрочка 30/60/90, новый клиент, уход и т.д.). ~2-3 дня.
5. **P3.5 — Расширенный парсер аналитики.** Заменить разовый `seed_data.py` на регулярный импорт «План vs Факт» через UI. ~1 неделя.
6. **P3.6 — Воронка продаж (deals).** Из design-doc. Только если бизнес попросит. ~1-2 недели.

> Из плана сознательно исключены: HTTPS+домен (по решению пользователя — остаёмся на IP), managed PostgreSQL (по решению — БД в контейнере).

---

## Контрольный лист сразу после завершения каждого этапа

- [ ] Записать в `agent_docs/development-history.md` итог этапа
- [ ] Обновить `agent_docs/index.md`, если появились новые документы
- [ ] Если принято важное решение — ADR в `agent_docs/adr.md`
- [ ] Свериться с `agent_docs/guides/dod.md`
- [ ] Commit и push
