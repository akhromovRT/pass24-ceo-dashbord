# Навигация по документам

Короткая навигация. Читать только релевантные файлы.

## Основные
- `agent_docs/architecture.md` — архитектура CEO24: компоненты, потоки данных, модель данных, стек.
- `agent_docs/adr.md` — архитектурные решения (монолит, SQLModel, снапшоты, источники данных).
- `agent_docs/development-history.md` — журнал итераций; смотреть последнюю запись.

## Дизайн и планы
- `docs/plans/2026-03-04-ceo24-mvp-design.md` — полный дизайн MVP: источники данных, модель, API, UI-экраны, метрики, дорожная карта.

## Спецификация и образцы данных
- Полная спецификация: `~/Downloads/_Spreadsheets/CEO24_Спецификация_системы.docx`
- Задолженность покупателей: `~/Downloads/_Spreadsheets/Задолженность покупателей за 2025 г. ООО  ОНВИ СЕРВИС.xls` (.xls формат — парсер поддерживает через xlrd)
- Банковская выписка: `~/Downloads/Выписка_40702810002630000347_03.03.2026.xlsx`
- Аналитика поступлений: `~/Library/Mobile Documents/com~apple~CloudDocs/ClaudeCode/Аналитика поступлений/Аналитика_поступлений_2025_2026.xlsx`

## Деплой
- Сервер: Timeweb VPS 85.239.51.34 (Ubuntu 24.04, обычный VPS — не managed)
- Стек: Docker Compose (PostgreSQL + FastAPI + Vue/Nginx)
- URL: http://85.239.51.34
- Доступ: `admin@onvi-service.ru` / пароль см. `~/.config/ceo24/credentials` (chmod 600, локально, не в репо)
- SSH: `ssh ceo24` (alias в `~/.ssh/config`, ключ `~/.ssh/ceo24_ed25519`)
- Compose-директория на сервере: `/root/pass24-ceo-dashbord/`
- Runbook: `agent_docs/guides/runbook.md` (см. ниже)

## Правила и гайды
- `agent_docs/guides/dod.md` — критерии завершенности (DoD).
- `agent_docs/guides/environment-setup.md` — настройка окружения; применять при инициализации проекта.
- `agent_docs/guides/logging.md` — логирование скриптов/интеграций.
- `agent_docs/guides/archiving-and-temp.md` — архивация и временные файлы.

## Шаблоны
- `agent_docs/templates/architecture.md`
- `agent_docs/templates/adr.md`
- `agent_docs/templates/development-history.md`
