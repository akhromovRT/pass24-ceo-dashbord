# Архив истории разработки

Записи, вытесненные из `development-history.md` по правилу «последние 10».
Читать при необходимости.

## Записи

### 2026-03-04 — Инициализация проекта

**Что сделано:**
- Изучена спецификация CEO24 v1.0 (12 разделов, модель данных, API, дорожная карта)
- Проанализированы 3 реальных файла-источника: задолженность покупателей (1593 строки, 243 покупателя), банковская выписка (35 строк за 1 день), аналитика поступлений (5 листов, 1780 детальных платежей)
- Выбран подход: классический монолит FastAPI + Vue 3 + PrimeVue + PostgreSQL
- Скоуп: MVP (6 недель) — парсер 1С, API, реестр клиентов, просрочки, базовый дашборд
- Заполнены проектные файлы: AGENTS.md, architecture.md, adr.md (5 решений), README.md
- Создан дизайн-документ: `docs/plans/2026-03-04-ceo24-mvp-design.md`

**Ключевые решения:** ADR-001..005 (монолит, SQLModel, иммутабельные снапшоты, три источника данных, расширенная модель organizations)

**Следующий шаг:** Создание implementation plan, scaffold проекта

### 2026-03-04 — Scaffold backend (Tasks 1-3)

**Что сделано:**
- Создан implementation plan: `docs/plans/2026-03-04-ceo24-mvp-implementation.md` (25 задач, 6 фаз)
- Task 1: Backend scaffold — pyproject.toml (hatchling), FastAPI app с CORS и /health, pydantic-settings конфиг, SQLModel database module
- Task 2: Docker Compose (postgres:16-alpine + backend) и Dockerfile. Docker не установлен на машине — файлы готовы к использованию
- Task 3: SQLModel модели — Organization (15+ полей, OrgType/OrgStatus enum), Contract (автоклассификация, ContractType enum), Document (DocType enum, denormalized org FK). 8 unit-тестов

**Окружение:**
- Python 3.12.12 через `uv` (venv в `backend/.venv`)
- Docker отсутствует на машине — для тестов используется SQLite in-memory
- Git-репозиторий инициализирован

**Ключевые решения:** ADR-006 (uv вместо pip для управления зависимостями)

**Следующий шаг:** Tasks 4-5 (остальные модели + Alembic миграции)
