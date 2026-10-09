"""Alert lifecycle: turn rule candidates into stored alerts without spamming (spec §10).

- Same dedupe key = same alert: updated in place, never duplicated.
- Dismissed alerts stay quiet unless they get more severe.
- Snoozed alerts come back after the snooze date.
- Alerts whose condition has gone away are marked resolved (and can reopen later).
- Every current condition is shown in the app; the daily email is what gets rate-limited
  (app.jobs.daily_alerts.MAX_DIGEST_ITEMS), so the in-app list never grows while you clear it.
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.planning.alert_rules import SEVERITY_RANK, Candidate, candidates
from app.modules.planning.models import Alert, PlanVersion
from app.modules.planning.simulation import WhatIf, simulate
from app.modules.planning.snapshot import Inputs, capture_inputs, load_inputs

VISIBLE = ("open",)


@dataclass
class SyncResult:
    created: List[Alert]
    reopened: List[Alert]
    resolved: List[Alert]


def previous_version(db: Session, user_id: str) -> Optional[Dict]:
    v = db.scalars(select(PlanVersion).where(PlanVersion.user_id == user_id).order_by(PlanVersion.number.desc())).first()
    if v is None:
        return None
    return {"id": v.id, "number": v.number, "as_of": v.as_of.isoformat(), "inputs": v.inputs, "outputs": v.outputs}


def evaluate(inp: Inputs, previous: Optional[Dict]) -> List[Candidate]:
    def salary_impact(actual_bps: int) -> int:
        base = simulate(inp, "base").summary
        slow = simulate(inp, "base", WhatIf(salary_growth_bps=actual_bps)).summary
        if base.net_worth_at_retirement_real_paise is None or slow.net_worth_at_retirement_real_paise is None:
            return 0
        return base.net_worth_at_retirement_real_paise - slow.net_worth_at_retirement_real_paise

    return candidates(inp, previous, simulate_fn=salary_impact)


def sync(db: Session, user_id: str, today: date, inp: Optional[Inputs] = None) -> SyncResult:
    inp = inp or load_inputs(capture_inputs(db, user_id, today))
    cands = sorted(evaluate(inp, previous_version(db, user_id)), key=lambda c: -c.rank_score)
    existing: Dict[str, Alert] = {a.dedupe_key: a for a in db.scalars(select(Alert).where(Alert.user_id == user_id))}
    now = datetime.now(timezone.utc)
    created: List[Alert] = []
    reopened: List[Alert] = []
    seen = set()
    for c in cands:
        seen.add(c.dedupe_key)
        a = existing.get(c.dedupe_key)
        fields = dict(rule_id=c.rule_id, family=c.family, severity=c.severity, title=c.title, message=c.message,
                      action_label=c.action_label, action_link=c.action_link, impact_paise=c.impact_paise,
                      rank_score=int(c.rank_score), data=c.data)
        if a is None:
            a = Alert(user_id=user_id, dedupe_key=c.dedupe_key, status="open", **fields)
            db.add(a)
            created.append(a)
            continue
        worse = SEVERITY_RANK[c.severity] > SEVERITY_RANK.get(a.severity, 0)
        for k, v in fields.items():
            setattr(a, k, v)
        if a.status == "resolved":
            a.status, a.resolved_at, a.notified_at = "open", None, None
            reopened.append(a)
        elif a.status == "dismissed" and a.dismissed_severity and SEVERITY_RANK[c.severity] > SEVERITY_RANK[a.dismissed_severity]:
            a.status, a.dismissed_severity, a.notified_at = "open", None, None
            reopened.append(a)
        elif a.status == "snoozed" and a.snoozed_until and a.snoozed_until <= today:
            a.status, a.snoozed_until = "open", None
            reopened.append(a)
        elif a.status == "open" and worse:
            a.notified_at = None  # escalation is news again
    resolved: List[Alert] = []
    for key, a in existing.items():
        if key not in seen and a.status in ("open", "snoozed", "dismissed"):
            a.status, a.resolved_at = "resolved", now
            resolved.append(a)
    db.commit()
    return SyncResult(created=created, reopened=reopened, resolved=resolved)


def visible(db: Session, user_id: str, include_hidden: bool = False) -> List[Alert]:
    q = select(Alert).where(Alert.user_id == user_id)
    if not include_hidden:
        q = q.where(Alert.status.in_(VISIBLE))
    else:
        q = q.where(Alert.status != "resolved")
    return sorted(db.scalars(q), key=lambda a: -a.rank_score)
