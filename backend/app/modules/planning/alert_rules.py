"""Alert rules (spec §10, module M10). Pure: current snapshot (+ last saved version) in,
candidate alerts out. Each alert says what happened, why it matters and what to do, and
has a stable dedupe key so it is raised once, not every day."""

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from app.calc.normalize import inr_text, monthly_equivalent_paise
from app.modules.planning.assumptions import effective, fingerprint
from app.modules.planning.goals import months_between

SEVERITY_RANK = {"info": 0, "opportunity": 1, "attention": 2, "warning": 3, "critical": 4}
SEVERITY_WEIGHT = {"critical": 1000, "warning": 600, "attention": 300, "opportunity": 200, "info": 50}


@dataclass
class Candidate:
    dedupe_key: str
    rule_id: str
    family: str
    severity: str
    title: str
    message: str
    action_label: Optional[str] = None
    action_link: Optional[str] = None
    impact_paise: Optional[int] = None
    data: Dict[str, Any] = field(default_factory=dict)

    @property
    def rank_score(self) -> float:
        impact = math.log10(max(1, (self.impact_paise or 0) // 100)) * 40 if self.impact_paise else 0
        return SEVERITY_WEIGHT[self.severity] + min(300, impact)


def _income(raw: Dict) -> int:
    return sum(monthly_equivalent_paise(i["amount_paise"], i["frequency"]) for i in raw.get("incomes", []) if i.get("is_active"))


def _discretionary(raw: Dict) -> int:
    return sum(monthly_equivalent_paise(e["amount_paise"], e["frequency"]) for e in raw.get("expenses", []) if e.get("bucket") == "discretionary")


def candidates(inp, previous: Optional[Dict[str, Any]] = None, simulate_fn=None) -> List[Candidate]:
    """`inp`: snapshot.Inputs. `previous`: {"as_of", "inputs", "outputs", "number"} of the last saved version."""
    out: List[Candidate] = []
    s, ef, debts, prot, gp = inp.summary, inp.emergency, inp.debts, inp.protection, inp.goals_plan
    a = inp.assumptions

    # ---- liquidity
    if ef.status in ("critical", "attention"):
        out.append(Candidate(
            "liquidity:emergency", "emergency_low", "liquidity", "critical" if ef.status == "critical" else "warning",
            "Emergency fund is below target" if ef.status == "attention" else "Less than a month of emergency cash",
            f"Your cash covers {ef.months_covered or 0} months of essentials; the minimum for you is {ef.target_months_low}. "
            "An unexpected bill or job loss would mean borrowing or selling investments.",
            f"Set aside {inr_text(ef.monthly_to_reach_low_in_12m_paise)} a month", "/safety", ef.gap_to_low_paise,
        ))

    # ---- debt
    if debts.high_cost_outstanding_paise:
        out.append(Candidate(
            "debt:high_cost", "high_cost_debt", "debt", "warning", "Expensive debt is still open",
            f"{inr_text(debts.high_cost_outstanding_paise)} is on a credit card or a loan at 14%+ a year. "
            "Clearing it is a guaranteed return higher than almost any investment.",
            "See payoff order", "/safety", debts.high_cost_outstanding_paise))
    if (debts.debt_to_income_bps or 0) > a.debt_to_income_high_bps:
        out.append(Candidate(
            "debt:burden", "debt_burden", "debt", "warning", "EMIs take a large share of income",
            f"EMIs are {debts.debt_to_income_bps / 100:.0f}% of take-home pay, leaving little for goals or surprises.",
            "Compare prepaying vs investing", "/safety", debts.total_emi_paise))

    # ---- protection
    if prot.life.status == "critical":
        out.append(Candidate("protection:life", "life_gap", "protection", "warning", "Your family may be under-protected",
                             f"Suggested life cover is {inr_text(prot.life.recommended_paise)}; you have {inr_text(prot.life.existing_paise)}.",
                             "See cover estimate", "/safety", prot.life.gap_paise))
    if prot.health.status == "critical":
        out.append(Candidate("protection:health", "health_gap", "protection", "warning", "No health insurance recorded",
                             "A single hospital stay can cost lakhs. Health cover protects your savings and goals.",
                             "See suggested cover", "/safety", prot.health.recommended_paise))
    for r in prot.renewals:
        lapsed = r.days_left < 0
        out.append(Candidate(
            f"protection:renewal:{r.policy_id}:{r.renewal_date.isoformat()}", "policy_renewal", "protection",
            "critical" if lapsed else "attention",
            f"{r.policy_type.replace('_', ' ').capitalize()} policy {'has lapsed' if lapsed else 'renews soon'}",
            f"Renewal date {r.renewal_date:%d %b %Y}" + (" has passed; you may not be covered." if lapsed else f", in {r.days_left} days."),
            "Update the policy", "/setup/insurance"))

    # ---- goals
    for g in gp.goals:
        if g.goal_status != "active" or not g.goal_id:
            continue
        if g.status in ("off_track", "at_risk"):
            out.append(Candidate(
                f"goal:{g.goal_id}", "goal_behind", "goals", "warning" if g.status == "off_track" else "attention",
                f"{g.name} is {'off track' if g.status == 'off_track' else 'at risk'}",
                f"At the current pace it is {(g.funded_bps or 0) / 100:.0f}% funded by its date. "
                + (f"It needs {inr_text(g.monthly_gap_paise)} more a month." if g.monthly_gap_paise else ""),
                "Try a what-if on this goal", f"/goals/{g.goal_id}",
                (g.monthly_gap_paise or 0) * max(1, g.months_left or 1), {"goal_id": g.goal_id}))
    for g in gp.goals:
        if g.goal_status == "achieved" and g.goal_id:
            out.append(Candidate(f"goal:{g.goal_id}:achieved", "goal_achieved", "goals", "info", f"{g.name}: achieved",
                                 "Well done. The money you were putting towards it can now go to your next goal.",
                                 "Review your goals", "/goals"))

    # ---- lifestyle
    if s.monthly_income_paise and s.monthly_discretionary_expenses_paise * 100 > 35 * s.monthly_income_paise:
        share = s.monthly_discretionary_expenses_paise * 100 // s.monthly_income_paise
        out.append(Candidate("lifestyle:share", "wants_high", "lifestyle", "attention", "Wants take a big share of income",
                             f"Discretionary spending is {share}% of income. Most budgeting rules keep it at 20–30%.",
                             "Compare budget rules", "/budget", s.monthly_discretionary_expenses_paise))

    # ---- changes since the last saved plan
    if previous is None:
        if any(x.status in ("on_track", "at_risk", "off_track") for x in gp.goals):
            out.append(Candidate("plan:first_version", "first_version", "plan", "info", "Save your first plan version",
                                 "Saving a version lets the app tell you what changed and whether you are still on track.",
                                 "Save a version", "/plan"))
        return out

    prev_in, prev_out = previous["inputs"], previous["outputs"]
    prev_date = date.fromisoformat(previous["as_of"])
    months = months_between(prev_date, inp.today)
    inc_then, inc_now = _income(prev_in), s.monthly_income_paise
    label = f"version {previous.get('number', '')}".strip()

    if inc_then > 0 and inc_now == 0:
        out.append(Candidate("career:interruption", "income_stopped", "career", "critical", "Your income has stopped",
                             f"Monthly income was {inr_text(inc_then)} at {label}; now none is recorded. "
                             f"Your emergency fund covers about {ef.months_covered or 0} months.",
                             "See how long your money lasts", "/journey"))
    elif inc_then > 0 and months >= 12:
        actual = ((inc_now / inc_then) ** (12 / months) - 1) * 10000
        growths = [i.expected_growth_bps for i in inp.state.incomes if i.is_active and i.kind == "salary" and i.expected_growth_bps is not None]
        assumed = sum(growths) / len(growths) if growths else a.salary_growth_bps
        if actual < assumed - 300:
            impact_text, impact = "", None
            if simulate_fn:
                try:
                    lost = simulate_fn(int(max(-2000, actual)))
                    if lost > 0:
                        impact, impact_text = lost, f" If this continues, your net worth at retirement is about {inr_text(lost)} lower in today's money."
                except Exception:  # never let a projection failure hide the alert itself
                    pass
            out.append(Candidate(
                f"career:salary_growth:{previous.get('id', label)}", "salary_below_plan", "career", "warning",
                "Income is growing slower than your plan assumes",
                f"Since {label} ({months} months ago) income grew {actual / 100:.1f}% a year; the plan assumes {assumed / 100:.1f}%.{impact_text}",
                "See recovery options", "/journey", impact, {"actual_bps": int(actual), "assumed_bps": int(assumed)}))

    if inc_then > 0 and inc_now >= inc_then * 110 // 100:
        rate_then = (prev_out.get("summary") or {}).get("savings_rate_bps") or 0
        if (s.savings_rate_bps or 0) < rate_then + 200:
            raise_amt = inc_now - inc_then
            out.append(Candidate(
                f"opportunity:raise:{inc_now}", "raise_not_saved", "lifestyle", "opportunity", "Put part of your raise to work",
                f"Income is up {inr_text(raise_amt)} a month since {label}, but your saving rate has not risen with it. "
                f"Saving half of the raise ({inr_text(raise_amt // 2)} a month) would speed up your goals.",
                "See what it does to your goals", "/goals", raise_amt // 2 * 12))

    disc_then, disc_now = _discretionary(prev_in), s.monthly_discretionary_expenses_paise
    if disc_then and inc_then and disc_now * inc_then > disc_then * inc_now * 105 // 100 and disc_now > disc_then:
        out.append(Candidate("lifestyle:creep", "lifestyle_creep", "lifestyle", "attention", "Lifestyle spending is growing faster than income",
                             f"Discretionary spending went from {inr_text(disc_then)} to {inr_text(disc_now)} a month since {label}.",
                             "Compare budget rules", "/budget", (disc_now - disc_then) * 12))

    now_loans = {x.id: x for x in inp.state.liabilities}
    for old in prev_in.get("liabilities", []):
        cur = now_loans.get(old["id"])
        if old.get("emi_paise") and old.get("outstanding_paise") and (cur is None or cur.outstanding_paise == 0):
            out.append(Candidate(f"opportunity:loan_closed:{old['id']}", "loan_closed", "debt", "opportunity",
                                 f"{old['name']} is paid off",
                                 f"The {inr_text(old['emi_paise'])} EMI is free now. Redirecting it keeps your lifestyle the same and speeds up goals.",
                                 "Add it to a goal", "/goals", old["emi_paise"] * 12))

    prev_hash = fingerprint(effective((prev_in.get("settings") or {}).get("assumption_overrides")))
    if prev_hash != fingerprint(a):
        out.append(Candidate(f"assumptions:{fingerprint(a)}", "assumptions_changed", "assumptions", "info",
                             "Assumptions changed since your last saved plan",
                             "Projections now use different inflation or return figures. Save a new version to keep a record.",
                             "Review changes", "/plan"))
    return out
