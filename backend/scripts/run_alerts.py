"""CLI: запустить генерацию алертов один раз.

Прод-cron (`/etc/cron.d/ceo24-alerts`):
  0 9 * * * docker compose -f /root/pass24-ceo-dashbord/docker-compose.yml \\
      exec -T backend python -m scripts.run_alerts

См. P3.4 в backlog. APScheduler не используем намеренно — системный cron
проще, без новых deps, без рисков двойного запуска при ребуте backend.
"""

import sys

from sqlmodel import Session

from app.core.database import engine
from app.services.alerts_scheduler import run_all


def main() -> int:
    with Session(engine) as session:
        result = run_all(session)
    total = sum(result.values())
    print(f"alerts created: total={total} {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
