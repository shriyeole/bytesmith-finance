"""AI onboarding chat: talk, watch the draft fill in, review, save everything in one go.

Endpoints (all under /api/v1, all scoped to the signed-in user):
  GET  /assistant/session            current chat (created on first visit)
  POST /assistant/session/messages   send a message; the model updates the draft and replies
  PUT  /assistant/session/draft      the user edits the draft directly (e.g. removes an item)
  POST /assistant/session/apply      save the draft as real records (all or nothing)
  POST /assistant/session/reset      start over

Privacy: message text is sent to the configured model and stored with the session; it is
never written to logs. Sessions are deleted with the account.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import Settings, get_settings
from app.core.models import User
from app.database import get_db
from app.modules.assistant import draft as d
from app.modules.assistant.llm import LLM, LLMError, make_llm
from app.modules.assistant.models import AssistantSession
from app.modules.assistant.prompt import GREETING, RESPONSE_SCHEMA, system_prompt
from app.modules.financial_state import models as m
from app.modules.financial_state.router import _asset_hook, _expense_hook, _values
from app.modules.financial_state.schemas import OnboardingStatus
from app.modules.financial_state.service import onboarding_status
from app.modules.planning.models import Goal
from app.modules.planning.router import _plain, _validate
from app.modules.planning.schemas import DEFAULT_PRIORITY, GoalType

router = APIRouter(prefix="/assistant", tags=["Assistant"])
log = logging.getLogger("app.assistant")

MAX_MESSAGE_CHARS = 4000
HISTORY_TURNS = 24  # messages sent to the model (the draft carries everything older)


# ------------------------------------------------------------------ dependencies

@lru_cache
def _cached_llm(api_key: str, model: str, endpoint: str) -> Optional[LLM]:
    return make_llm(api_key, model, endpoint)


def get_llm(settings: Settings = Depends(get_settings)) -> Optional[LLM]:
    return _cached_llm(settings.gemini_api_key, settings.gemini_model, settings.gemini_endpoint)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return date.today()


# ------------------------------------------------------------------ schemas

class ChatMessage(BaseModel):
    role: str
    text: str


class Section(BaseModel):
    key: str
    label: str
    done: bool
    count: int
    missing: List[str]


class SessionRead(BaseModel):
    id: str
    status: str
    messages: List[ChatMessage]
    draft: d.Draft
    sections: List[Section]
    complete: bool
    ai_available: bool
    messages_left_today: int


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ApplyResult(BaseModel):
    onboarding: OnboardingStatus
    created: dict


# ------------------------------------------------------------------ helpers

def _active(db: Session, user: User) -> AssistantSession:
    s = db.scalars(select(AssistantSession).where(AssistantSession.user_id == user.id, AssistantSession.status == "active")
                   .order_by(AssistantSession.created_at.desc())).first()
    if s is None:
        s = AssistantSession(user_id=user.id, messages=[{"role": "assistant", "text": GREETING, "at": _now().isoformat()}],
                             draft=d.Draft().model_dump(mode="json"), user_turns=0)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def _load_draft(s: AssistantSession) -> d.Draft:
    try:
        return d.clean(d.Draft.model_validate(s.draft or {}))
    except ValidationError:
        return d.Draft()


def _messages_today(db: Session, user: User) -> int:
    since = (_now() - timedelta(hours=24)).isoformat()
    sessions = db.scalars(select(AssistantSession).where(AssistantSession.user_id == user.id)).all()
    return sum(1 for s in sessions for msg in (s.messages or []) if msg.get("role") == "user" and msg.get("at", "") >= since)


def _extract_draft(out: dict) -> dict:
    """The draft as an object, whichever way the model shaped it."""
    raw = out.get("draft")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    if not isinstance(raw, dict):
        top = {k: v for k, v in out.items() if k in d.Draft.model_fields}
        raw = top or {}
    return raw


def _is_empty(draft: d.Draft) -> bool:
    lists = ("family", "incomes", "expenses", "assets", "loans", "insurance", "goals")
    return (not any(getattr(draft, k) for k in lists) and not draft.none_declared
            and all(v is None for v in draft.profile.model_dump().values()))


def _read(db: Session, user: User, s: AssistantSession, settings: Settings, llm: Optional[LLM]) -> SessionRead:
    draft = _load_draft(s)
    sections = d.progress(draft, _today())
    return SessionRead(
        id=s.id, status=s.status,
        messages=[ChatMessage(role=x["role"], text=x["text"]) for x in (s.messages or [])],
        draft=draft,
        sections=[Section(**sec.__dict__) for sec in sections],
        complete=d.is_complete(sections),
        ai_available=llm is not None,
        messages_left_today=max(0, settings.assistant_daily_messages - _messages_today(db, user)),
    )


# ------------------------------------------------------------------ endpoints

@router.get("/session", response_model=SessionRead)
def get_session(db: Session = Depends(get_db), user: User = Depends(get_current_user),
                settings: Settings = Depends(get_settings), llm: Optional[LLM] = Depends(get_llm)):
    return _read(db, user, _active(db, user), settings, llm)


@router.post("/session/messages", response_model=SessionRead)
def send_message(payload: MessageIn, db: Session = Depends(get_db), user: User = Depends(get_current_user),
                 settings: Settings = Depends(get_settings), llm: Optional[LLM] = Depends(get_llm)):
    if llm is None:
        raise HTTPException(503, "The setup assistant is not switched on yet. Please use the step-by-step forms.")
    if _messages_today(db, user) >= settings.assistant_daily_messages:
        raise HTTPException(429, "You've reached today's chat limit. Your answers are kept — continue tomorrow or use the forms.")
    s = _active(db, user)
    text = payload.text.strip()
    if not text:
        raise HTTPException(422, "Message is empty.")
    draft = _load_draft(s)
    today = _today()
    history = [{"role": x["role"], "text": x["text"]} for x in (s.messages or [])][-HISTORY_TURNS:]
    history.append({"role": "user", "text": text})

    reply: str
    try:
        out = llm.generate(system=system_prompt(draft, d.progress(draft, today), today), history=history, schema=RESPONSE_SCHEMA)
        new_draft = d.clean(d.Draft.model_validate(_extract_draft(out)))
        if _is_empty(new_draft) and not _is_empty(draft):
            # A reply that drops everything is a model slip, not the user deleting their data.
            log.warning("Model returned an empty draft (keys=%s); keeping the previous one", sorted(out)[:12])
            new_draft = draft
        reply = str(out.get("reply") or "").strip()[:2000] or "Got it. Anything else?"
        draft = new_draft
    except LLMError as exc:
        log.warning("Assistant turn failed: %s", exc)  # details already logged by the client
        if exc.status in (402, 429):
            reply = ("The assistant has hit its usage limit right now, so I couldn't read that. Your message is kept — "
                     "try again a bit later, or use the step-by-step forms.")
        elif exc.status in (401, 403):
            reply = "The assistant isn't set up correctly yet (the AI key was refused). Please use the forms for now."
        else:
            reply = "Sorry, I couldn't process that just now. Could you send it again?"
    except (ValidationError, AttributeError, TypeError) as exc:
        log.warning("Assistant turn failed: model output had the wrong shape (%s)", type(exc).__name__)
        reply = "Sorry, I couldn't process that just now. Could you send it again?"

    now = _now().isoformat()
    s.messages = [*(s.messages or []), {"role": "user", "text": text, "at": now}, {"role": "assistant", "text": reply, "at": now}]
    s.draft = draft.model_dump(mode="json")
    s.user_turns = (s.user_turns or 0) + 1
    db.commit()
    db.refresh(s)
    return _read(db, user, s, settings, llm)


@router.put("/session/draft", response_model=SessionRead)
def edit_draft(payload: d.Draft, db: Session = Depends(get_db), user: User = Depends(get_current_user),
               settings: Settings = Depends(get_settings), llm: Optional[LLM] = Depends(get_llm)):
    s = _active(db, user)
    s.draft = d.clean(payload).model_dump(mode="json")
    db.commit()
    db.refresh(s)
    return _read(db, user, s, settings, llm)


@router.post("/session/reset", response_model=SessionRead)
def reset_session(db: Session = Depends(get_db), user: User = Depends(get_current_user),
                  settings: Settings = Depends(get_settings), llm: Optional[LLM] = Depends(get_llm)):
    s = _active(db, user)
    s.status = "reset"
    db.commit()
    return _read(db, user, _active(db, user), settings, llm)


@router.post("/session/apply", response_model=ApplyResult)
def apply_session(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s = _active(db, user)
    draft = _load_draft(s)
    today = _today()
    if _is_empty(draft):
        raise HTTPException(422, {"message": "Nothing to save yet.", "problems": ["Nothing has been captured yet — tell the assistant about your money first."]})
    try:
        rec = d.to_records(draft, today)
    except d.DraftError as exc:
        raise HTTPException(422, {"message": "Some details need fixing before saving.", "problems": exc.problems})

    created = {"members": 0, "incomes": 0, "expenses": 0, "assets": 0, "liabilities": 0, "insurance": 0, "goals": 0}
    try:
        # Profile (merge into any existing one)
        values = _values(rec.profile, partial=True)
        profile = db.get(m.HouseholdProfile, user.id)
        if profile is None:
            profile = m.HouseholdProfile(user_id=user.id)
            db.add(profile)
        for k, v in values.items():
            if v is not None:
                setattr(profile, k, v)

        def add(model, payload, key, hook=None):
            vals = _values(payload, partial=False)
            if hook:
                vals = hook(vals, None)
            db.add(model(user_id=user.id, **vals))
            created[key] += 1

        for x in rec.members:
            add(m.HouseholdMember, x, "members")
        for x in rec.incomes:
            add(m.IncomeStream, x, "incomes")
        for x in rec.expenses:
            add(m.Expense, x, "expenses", _expense_hook)
        for x in rec.assets:
            add(m.Asset, x, "assets", _asset_hook)
        for x in rec.liabilities:
            add(m.Liability, x, "liabilities")
        for x in rec.policies:
            add(m.InsurancePolicy, x, "insurance")
        db.flush()

        has_retirement = db.scalars(select(Goal).where(Goal.user_id == user.id, Goal.goal_type == "retirement",
                                                       Goal.status != "achieved")).first() is not None
        for g in rec.goals:
            vals = _plain(g, partial=False)
            if vals["goal_type"] == GoalType.RETIREMENT.value and has_retirement:
                continue  # keep the one they already have
            vals["priority"] = vals.get("priority") or DEFAULT_PRIORITY[g.goal_type].value
            _validate(vals, db, user)
            db.add(Goal(user_id=user.id, **vals))
            created["goals"] += 1

        # Mark answered steps done, as the forms would.
        step_for = {"income": "income", "expenses": "expenses", "assets": "assets", "loans": "liabilities", "insurance": "insurance"}
        done = {step_for[k] for k in rec.answered}
        if not draft.incomes and draft.profile.employment_type == "not_working":
            done.add("income")
        state = db.get(m.OnboardingState, user.id)
        if state is None:
            state = m.OnboardingState(user_id=user.id, completed_steps=[])
            db.add(state)
        state.completed_steps = sorted(set(state.completed_steps or []) | done)

        s.status = "applied"
        s.applied_at = _now()
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    return ApplyResult(onboarding=onboarding_status(db, user.id), created=created)
