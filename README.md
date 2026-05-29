# CEO24

Управленческая информационная система для ООО «ОНВИ СЕРВИС».

Аналитика в реальном времени: биллинг абонентской платы, контроль должников, сводный дашборд CEO.

## Стек

- **Backend:** Python 3.12 + FastAPI + SQLModel + PostgreSQL 16
- **Frontend:** Vue 3 + TypeScript + PrimeVue + vue-echarts
- **Инфраструктура:** Docker + nginx

## Быстрый старт

```bash
docker-compose up -d
```

Backend: http://localhost:8000 (Swagger UI `/docs` — только если `DEBUG=true` в `backend/.env`, см. ADR-021)
Frontend: http://localhost:3000

## Структура

```
├── backend/           # FastAPI + SQLModel
│   ├── app/
│   │   ├── api/       # REST endpoints
│   │   ├── models/    # SQLModel-модели
│   │   ├── services/  # Бизнес-логика
│   │   ├── parser/    # Парсер 1С (XLS/XLSX)
│   │   └── core/      # Конфиг, security, DB
│   ├── alembic/       # Миграции
│   └── tests/
├── frontend/          # Vue 3 SPA
│   └── src/
│       ├── views/     # Страницы
│       ├── components/
│       ├── stores/    # Pinia
│       └── api/       # HTTP-клиент
├── docker-compose.yml
├── nginx/
└── agent_docs/        # Проектная документация
```

## Документация

- `AGENTS.md` — правила работы и контекст проекта
- `agent_docs/index.md` — карта документов
- `agent_docs/architecture.md` — архитектура
- `docs/plans/` — дизайн-документы
