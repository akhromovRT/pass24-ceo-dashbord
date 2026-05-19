# Навигация по документам

Короткая навигация. Читать только релевантные файлы.

## Основные
- `agent_docs/architecture.md` — архитектура CEO24: компоненты, потоки данных, модель данных, стек.
- `agent_docs/adr.md` — архитектурные решения (монолит, SQLModel, снапшоты, источники данных).
- `agent_docs/development-history.md` — журнал итераций; смотреть последнюю запись.
- `agent_docs/backlog.md` — список идей и рекомендаций для развития.

## Дизайн и планы
- `docs/plans/2026-03-04-ceo24-mvp-design.md` — полный дизайн MVP: источники данных, модель, API, UI-экраны, метрики, дорожная карта.

## Спецификация и образцы данных
- Полная спецификация: `~/Downloads/_Spreadsheets/CEO24_Спецификация_системы.docx`
- Задолженность покупателей: `~/Downloads/_Spreadsheets/Задолженность покупателей за 2025 г. ООО  ОНВИ СЕРВИС.xls` (.xls формат — парсер поддерживает через xlrd)
- Банковская выписка: `~/Downloads/Выписка_40702810002630000347_03.03.2026.xlsx`
- Аналитика поступлений: `~/Library/Mobile Documents/com~apple~CloudDocs/ClaudeCode/Аналитика поступлений/Аналитика_поступлений_2025_2026.xlsx`

## Деплой
- Сервер: Timeweb VPS 85.239.51.34 (Ubuntu 24.04, обычный VPS — не managed)
- Домен: `ceo.pass24pro.ru` (A-запись → 85.239.51.34)
- Стек: Docker Compose (PostgreSQL + FastAPI + Vue/Nginx)
- URL: https://ceo.pass24pro.ru (HTTPS — Let's Encrypt; HTTP редиректит на HTTPS)
- Пользователи: `admin@onvi-service.ru` (технический), `akhromov@pass24online.ru` (Алексей Хромов) — оба admin. Пароли в `~/.config/ceo24/credentials` (chmod 600, локально, не в репо)
- Управление пользователями: UI `/users` (admin-only) или CLI: `ssh ceo24 'docker exec -it $(docker ps -qf name=backend) python scripts/manage_users.py --help'`
- SSH: `ssh ceo24` (alias в `~/.ssh/config`, ключ `~/.ssh/ceo24_ed25519`)
- Compose-директория на сервере: `/root/pass24-ceo-dashbord/`
- Runbook: `agent_docs/guides/runbook.md` (см. ниже)

## Правила и гайды
- `agent_docs/guides/dod.md` — критерии завершенности (DoD).
- `agent_docs/guides/environment-setup.md` — настройка окружения; применять при инициализации проекта.
- `agent_docs/guides/logging.md` — логирование скриптов/интеграций.
- `agent_docs/guides/archiving-and-temp.md` — архивация и временные файлы.
- `agent_docs/guides/runbook.md` — операционный runbook production-сервера.
- `agent_docs/guides/import-accountant.md` — инструкция для бухгалтера: импорт выгрузок 1С (оплаты ежедневно, долги еженедельно) и где проверять результат.
- `agent_docs/guides/dashboard-metrics.md` — памятка для сотрудников: что означает каждый показатель раздела Dashboard и как его анализировать.

## Шаблоны
- `agent_docs/templates/architecture.md`
- `agent_docs/templates/adr.md`
- `agent_docs/templates/development-history.md`
