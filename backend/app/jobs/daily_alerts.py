"""Daily alert run: re-check every user's plan, then send one digest per user with any new
critical or warning alerts. Run with `python -m app.jobs.daily_alerts` (Cloud Run Job,
triggered daily by Cloud Scheduler)."""

import logging
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.models import User
from app.database import SessionLocal
from app.jobs.notify import LogNotifier, Notifier
from app.modules.planning import alerts as alert_service
from app.modules.planning.models import Alert

log = logging.getLogger("bytesmith.jobs.daily_alerts")
NOTIFY_SEVERITIES = ("critical", "warning")
MAX_DIGEST_ITEMS = 5  # one short email a day at most; the rest wait in the app


def run(db: Session, today: date, notifier: Notifier) -> dict:
    stats = {"users": 0, "failed": 0, "created": 0, "digests": 0}
    for (user_id, email) in db.execute(select(User.id, User.email)).all():
        stats["users"] += 1
        try:
            res = alert_service.sync(db, user_id, today)
            stats["created"] += len(res.created)
            pending = db.scalars(select(Alert).where(
                Alert.user_id == user_id, Alert.status == "open", Alert.notified_at.is_(None),
                Alert.severity.in_(NOTIFY_SEVERITIES)).order_by(Alert.rank_score.desc()).limit(MAX_DIGEST_ITEMS)).all()
            if pending:
                items = [{"rule_id": a.rule_id, "severity": a.severity, "title": a.title, "link": a.action_link} for a in pending]
                if notifier.send_digest(user_id, email, items):
                    now = datetime.now(timezone.utc)
                    for a in pending:
                        a.notified_at = now
                    db.commit()
                    stats["digests"] += 1
        except Exception:  # one bad account must not stop the run
            db.rollback()
            stats["failed"] += 1
            log.exception("alert sync failed for user %s", user_id)
    return stats


def main(today: Optional[date] = None) -> dict:
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        stats = run(db, today or date.today(), LogNotifier())
    log.info("daily alerts done: %s", stats)
    return stats


if __name__ == "__main__":
    main()
