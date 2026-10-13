import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ClientError } from '../api/http';
import { useApplyChat, useChatSession, useEditDraft, useResetChat, useSendMessage } from '../api/assistant';
import type { ChatSession, Draft } from '../api/assistant';
import { formatINR } from '../utils/currency';

/** Rupees (as the draft holds them) to display text. */
const inr = (rupees: number | null | undefined) => (rupees === null || rupees === undefined ? '—' : formatINR(rupees * 100));
const nice = (s: string | null | undefined) => (s ? s.replace(/_/g, ' ') : '');
const per = (f: string | null | undefined) => (!f || f === 'monthly' ? '/month' : f === 'yearly' ? '/year' : ` ${nice(f)}`);

const EXAMPLE =
  "I'm 32, salaried in Pune, take home ₹1.2L a month. Rent 25k, groceries and bills about 20k, eating out 8k. " +
  "₹3L in savings, ₹5L in mutual funds with a 10k SIP. Car loan ₹4L left, EMI 12k. Health cover ₹5L from office. " +
  'Married, one kid aged 3. Want a ₹80L house in 5 years and to retire at 55.';

type ListKey = 'incomes' | 'expenses' | 'assets' | 'loans' | 'insurance' | 'family' | 'goals';
const SECTION_LIST: Record<string, ListKey | null> = {
  profile: null, income: 'incomes', expenses: 'expenses', assets: 'assets', loans: 'loans', insurance: 'insurance', family: 'family', goals: 'goals',
};

/** One line per captured item, in plain words. */
function itemLines(draft: Draft, key: ListKey): string[] {
  switch (key) {
    case 'incomes': return draft.incomes.map((i) => `${i.name} · ${inr(i.amount)}${per(i.frequency)}`);
    case 'expenses': return draft.expenses.map((e) => `${e.name} · ${inr(e.amount)}${per(e.frequency)}`);
    case 'assets': return draft.assets.map((a) => `${a.name} · ${inr(a.value)}${a.monthly_investment ? ` + ${inr(a.monthly_investment)}/month` : ''}${a.is_emergency_fund ? ' · emergency fund' : ''}`);
    case 'loans': return draft.loans.map((l) => `${l.name} · ${inr(l.outstanding)} left${l.emi ? ` · EMI ${inr(l.emi)}` : ''}${l.interest_rate_pct ? ` · ${l.interest_rate_pct}%` : ''}`);
    case 'insurance': return draft.insurance.map((x) => `${nice(x.policy_type) || 'Policy'} · cover ${inr(x.cover)}${x.source === 'employer' ? ' · from employer' : x.annual_premium ? ` · ${inr(x.annual_premium)}/year` : ''}`);
    case 'family': return draft.family.map((m) => `${m.name} · ${nice(m.relationship)}${m.age !== null && m.age !== undefined ? ` · ${m.age} yrs` : ''}`);
    case 'goals': return draft.goals.map((g) => g.goal_type === 'retirement'
      ? `${g.name} · retire at ${draft.profile.retirement_age ?? '—'}`
      : `${g.name} · ${inr(g.cost_today)} by ${g.target_year ?? '—'}${g.saved ? ` · ${inr(g.saved)} saved` : ''}`);
    default: return [];
  }
}

function profileLines(draft: Draft): string[] {
  const p = draft.profile;
  return [
    p.full_name,
    p.age ? `${p.age} years old` : p.date_of_birth ? `Born ${p.date_of_birth}` : null,
    [nice(p.employment_type), p.city].filter(Boolean).join(' · ') || null,
    nice(p.marital_status) || null,
    p.retirement_age ? `Retire at ${p.retirement_age}` : null,
  ].filter(Boolean) as string[];
}

/** Light formatting for assistant text: paragraphs and line breaks only. */
const Bubble: React.FC<{ role: string; text: string }> = ({ role, text }) => (
  <div className={`chat__msg chat__msg--${role === 'user' ? 'user' : 'bot'}`}>
    {text.split(/\n{2,}/).map((para, i) => <p key={i}>{para.split('\n').map((l, j) => <React.Fragment key={j}>{j > 0 && <br />}{l}</React.Fragment>)}</p>)}
  </div>
);

const Captured: React.FC<{
  session: ChatSession; onRemove?: (key: ListKey, index: number) => void; open: boolean;
}> = ({ session, onRemove, open }) => {
  const { draft, sections } = session;
  const done = sections.filter((s) => s.done).length;
  return (
    <div className="captured">
      <div className="captured__head">
        <h2 className="captured__title">Your setup</h2>
        <span className="captured__count">{done} of {sections.length}</span>
      </div>
      <div className="captured__bar" role="progressbar" aria-valuemin={0} aria-valuemax={sections.length} aria-valuenow={done} aria-label="Setup progress">
        <span style={{ width: `${(done / sections.length) * 100}%` }} />
      </div>
      {open && (
        <ul className="captured__list">
          {sections.map((sec) => {
            const key = SECTION_LIST[sec.key];
            const lines = key ? itemLines(draft, key) : profileLines(draft);
            const none = key && draft.none_declared.includes(sec.key) && lines.length === 0;
            return (
              <li key={sec.key} className={`captured__sec ${sec.done ? 'is-done' : ''}`}>
                <div className="captured__sec-head">
                  <span className="captured__dot" aria-hidden>{sec.done ? '✓' : ''}</span>
                  <span className="captured__label">{sec.label}</span>
                  <span className="sr-only">{sec.done ? 'done' : 'not done'}</span>
                </div>
                {lines.length > 0 && (
                  <ul className="captured__items">
                    {lines.map((line, i) => (
                      <li key={i}>
                        <span>{line}</span>
                        {key && onRemove && (
                          <button type="button" className="captured__remove" aria-label={`Remove ${line}`} onClick={() => onRemove(key, i)}>×</button>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
                {none && <p className="captured__none">None</p>}
                {!sec.done && sec.missing.length > 0 && <p className="captured__missing">Needs: {sec.missing.join(', ')}</p>}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};

export const StartPage: React.FC = () => {
  const session = useChatSession();
  const send = useSendMessage();
  const edit = useEditDraft();
  const reset = useResetChat();
  const apply = useApplyChat();
  const navigate = useNavigate();
  const [text, setText] = useState('');
  const [pending, setPending] = useState<string | null>(null);
  const [showPanel, setShowPanel] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const s = session.data;

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [s?.messages.length, pending]);

  const problems = useMemo(() => {
    const err = apply.error;
    if (err instanceof ClientError && err.status === 422) {
      const detail = (err.details as { detail?: { problems?: string[] } } | null)?.detail;
      return detail?.problems ?? [err.message];
    }
    return null;
  }, [apply.error]);

  if (session.isLoading) return <div className="page-container"><p className="muted">Loading…</p></div>;
  if (session.isError || !s) return <div className="page-container"><div className="form-alert form-alert--error">{(session.error as Error)?.message ?? 'Could not load the chat.'}</div></div>;

  const userTurns = s.messages.filter((m) => m.role === 'user').length;
  const submit = (value: string) => {
    const v = value.trim();
    if (!v || send.isPending) return;
    setPending(v);
    setText('');
    send.mutate(v, {
      onSettled: () => setPending(null),
      onError: () => setText(v), // give the text back so nothing is lost
    });
  };
  const removeItem = (key: ListKey, index: number) => {
    const draft: Draft = { ...s.draft, [key]: (s.draft[key] as unknown[]).filter((_, i) => i !== index) } as Draft;
    edit.mutate(draft);
  };
  const save = () => apply.mutate(undefined, { onSuccess: () => navigate('/overview', { replace: true }) });

  return (
    <div className="page-container start">
      <header className="page-header-row">
        <div>
          <h1 className="page-title">Let's set up your plan</h1>
          <p className="page-subtitle">Chat instead of filling forms. Nothing is saved until you review it.</p>
        </div>
        <div className="start__header-links">
          <Link to="/setup/profile" className="btn-link">Use forms instead</Link>
          {userTurns > 0 && (
            <button type="button" className="btn-link btn-link--danger" disabled={reset.isPending}
              onClick={() => { if (window.confirm('Start over? The chat and everything captured so far will be cleared.')) reset.mutate(); }}>
              Start over
            </button>
          )}
        </div>
      </header>

      {!s.ai_available && (
        <div className="form-alert form-alert--error" role="alert">
          The chat assistant isn't switched on yet. <Link to="/setup/profile">Set up with the step-by-step forms</Link>.
        </div>
      )}

      <div className="start__grid">
        <section className="card chat" aria-label="Setup chat">
          <div className="chat__log" aria-live="polite">
            {s.messages.map((m, i) => <Bubble key={i} role={m.role} text={m.text} />)}
            {pending && <Bubble role="user" text={pending} />}
            {pending && <div className="chat__msg chat__msg--bot chat__typing" aria-label="Assistant is typing"><span /><span /><span /></div>}
            {userTurns === 0 && !pending && s.ai_available && (
              <div className="chat__starters">
                <button type="button" className="chip" onClick={() => { setText(EXAMPLE); inputRef.current?.focus(); }}>Use the example to try it</button>
                <button type="button" className="chip" onClick={() => submit("Let's go one question at a time.")}>Ask me one question at a time</button>
              </div>
            )}
            <div ref={endRef} />
          </div>

          {send.isError && <div className="form-alert form-alert--error chat__error">{(send.error as Error).message}</div>}

          {s.complete && !reviewing && (
            <div className="chat__ready">
              <span>Everything's in. Check it and save.</span>
              <button type="button" className="btn btn--primary btn--sm" onClick={() => setReviewing(true)}>Review & save</button>
            </div>
          )}

          <form className="chat__composer" onSubmit={(e) => { e.preventDefault(); submit(text); }}>
            <label htmlFor="chat-input" className="sr-only">Your message</label>
            <textarea
              id="chat-input" ref={inputRef} value={text} rows={text.length > 120 ? 4 : 2} maxLength={4000}
              placeholder={userTurns === 0 ? 'Tell me about your money in your own words…' : 'Type your answer…'}
              disabled={!s.ai_available || s.messages_left_today === 0}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(text); } }}
            />
            <button type="submit" className="btn btn--primary" disabled={!text.trim() || send.isPending || !s.ai_available}>
              {send.isPending ? 'Sending…' : 'Send'}
            </button>
          </form>
          <p className="chat__fine">
            Your messages are processed by Google Gemini to fill in your details. Enter to send · Shift+Enter for a new line
            {s.messages_left_today <= 10 ? ` · ${s.messages_left_today} messages left today` : ''}
          </p>
        </section>

        <aside className={`card start__panel ${showPanel ? 'is-open' : ''}`}>
          <Captured session={s} open onRemove={removeItem} />
          <button type="button" className="btn-link start__panel-toggle" onClick={() => setShowPanel((v) => !v)}>
            {showPanel ? 'Hide details' : 'Show what I have so far'}
          </button>
          <button type="button" className="btn btn--outline start__review" disabled={userTurns === 0} onClick={() => setReviewing(true)}>
            Review & save
          </button>
        </aside>
      </div>

      {reviewing && (
        <div className="review-overlay" role="dialog" aria-modal="true" aria-labelledby="review-title">
          <div className="card review">
            <h2 id="review-title" className="review__title">Check your details</h2>
            <p className="muted">Remove anything that's wrong, or close this and tell the assistant what to change.</p>
            {!s.complete && (
              <div className="form-alert form-alert--error">
                Some things are still missing: {s.sections.filter((x) => !x.done).map((x) => x.label).join(', ')}.
                You can save now and add them later.
              </div>
            )}
            <Captured session={s} open onRemove={removeItem} />
            {problems && (
              <div className="form-alert form-alert--error" role="alert">
                <p>Please fix these first (just tell the assistant):</p>
                <ul>{problems.map((p) => <li key={p}>{p}</li>)}</ul>
              </div>
            )}
            {apply.isError && !problems && <div className="form-alert form-alert--error">{(apply.error as Error).message}</div>}
            <div className="review__actions">
              <button type="button" className="btn btn--outline" onClick={() => { setReviewing(false); apply.reset(); }}>Keep chatting</button>
              <button type="button" className="btn btn--primary" disabled={apply.isPending} onClick={save}>
                {apply.isPending ? 'Saving…' : 'Save my plan'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
