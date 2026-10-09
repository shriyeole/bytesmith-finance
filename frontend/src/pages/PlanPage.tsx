import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { PlanDiff, useAssumptions, useChanges, usePublishVersion, useSaveAssumptions, useVersions, verifyVersion, VerifyResult } from '../api/plan';
import { day, inr, inrShort, STATUS_LABEL } from '../features/planning/format';
import { Pill } from '../features/planning/ui';
import { bpsToPercent, percentToBps } from '../utils/money';

const Changes: React.FC<{ d: PlanDiff }> = ({ d }) => (
  <div className="changes">
    <p className="changes__summary">{d.summary}</p>
    {d.metric_changes.length > 0 && (
      <div className="table-wrap">
        <table className="data-table">
          <thead><tr><th>What it means</th><th>{d.from_label}</th><th>{d.to_label}</th><th>Change</th></tr></thead>
          <tbody>
            {d.metric_changes.map((m) => (
              <tr key={m.metric}>
                <td>{m.metric}</td>
                <td>{m.kind === 'money' ? inr(m.before) : m.before ?? '—'}</td>
                <td>{m.kind === 'money' ? inr(m.after) : m.after ?? '—'}</td>
                <td className={m.improved == null ? '' : m.improved ? 'delta-up' : 'delta-down'}>
                  {m.delta == null ? '—' : `${m.delta > 0 ? '+' : ''}${m.kind === 'money' ? inr(m.delta) : Math.round(m.delta * 10) / 10}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
    {d.goal_changes.length > 0 && (
      <ul className="change-list">
        {d.goal_changes.map((g) => (
          <li key={g.name}>
            <strong>{g.name}</strong>: {g.before_status ? STATUS_LABEL[g.before_status] : 'new'} → {g.after_status ? STATUS_LABEL[g.after_status] : 'removed'}
            {g.before_required_paise !== g.after_required_paise && g.after_required_paise != null && <span className="muted"> · needs {inr(g.after_required_paise)}/month{g.before_required_paise != null ? ` (was ${inr(g.before_required_paise)})` : ''}</span>}
          </li>
        ))}
      </ul>
    )}
    {(d.input_changes.length > 0 || d.assumption_changes.length > 0) && (
      <details className="method" open={d.input_changes.length <= 6}>
        <summary>What you changed ({d.input_changes.length + d.assumption_changes.length})</summary>
        <ul>{[...d.input_changes.map((c) => `${c.area}: ${c.text}`), ...d.assumption_changes.map((a) => `Assumption — ${a}`)].map((t) => <li key={t}>{t}</li>)}</ul>
      </details>
    )}
  </div>
);

const FIELDS: { key: string; label: string; kind: 'pct' | 'years' }[] = [
  { key: 'general_inflation_bps', label: 'Inflation', kind: 'pct' },
  { key: 'education_inflation_bps', label: 'Education inflation', kind: 'pct' },
  { key: 'post_retirement_return_bps', label: 'Return after retirement', kind: 'pct' },
  { key: 'life_expectancy_years', label: 'Plan to age', kind: 'years' },
  { key: 'home_loan_rate_bps', label: 'Home-loan interest', kind: 'pct' },
  { key: 'home_down_payment_bps', label: 'Home down payment', kind: 'pct' },
];
const BANDS = ['Goals under 2 yrs', '2–7 yrs', '7–15 yrs', 'Over 15 yrs'];

const AssumptionsEditor: React.FC = () => {
  const q = useAssumptions();
  const { save, reset } = useSaveAssumptions();
  const [form, setForm] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const a = q.data;

  useEffect(() => {
    if (!a) return;
    const o = a.overrides as Record<string, number | number[]>;
    const f: Record<string, string> = {};
    for (const fd of FIELDS) f[fd.key] = o[fd.key] == null ? '' : fd.kind === 'pct' ? bpsToPercent(o[fd.key] as number) : String(o[fd.key]);
    const r = o.return_by_horizon_bps as number[] | undefined;
    BANDS.forEach((_, i) => { f[`ret${i}`] = r ? bpsToPercent(r[i]) : ''; });
    setForm(f);
  }, [a]);

  if (!a) return <p className="muted">Loading…</p>;
  const eff = a.effective as Record<string, unknown>;
  const defaults = a.defaults as Record<string, unknown>;
  const defReturns = (defaults.return_by_horizon as { return_bps: number }[]).map((x) => x.return_bps);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    try {
      const changes: Record<string, number | number[] | null> = {};
      for (const fd of FIELDS) {
        const raw = form[fd.key]?.trim() ?? '';
        if (raw === '') changes[fd.key] = null;
        else if (fd.kind === 'pct') changes[fd.key] = percentToBps(raw);
        else if (/^\d+$/.test(raw)) changes[fd.key] = Number(raw);
        else throw new Error(`${fd.label}: enter a whole number`);
      }
      const rets = BANDS.map((_, i) => form[`ret${i}`]?.trim() ?? '');
      if (rets.every((x) => x === '')) changes.return_by_horizon_bps = null;
      else changes.return_by_horizon_bps = rets.map((x, i) => (x === '' ? defReturns[i] : (percentToBps(x) as number)));
      await save.mutateAsync(changes);
    } catch (ex) {
      setErr((ex as Error).message);
    }
  };

  return (
    <form className="assumptions" onSubmit={submit}>
      <div className="form-grid form-grid--3">
        {FIELDS.map((fd) => (
          <div key={fd.key} className="form-field">
            <label className="form-field__label" htmlFor={`as-${fd.key}`}>{fd.label}{fd.kind === 'pct' ? ' %' : ''}</label>
            <input id={`as-${fd.key}`} className="text-input" inputMode="decimal" value={form[fd.key] ?? ''} onChange={(e) => setForm((f) => ({ ...f, [fd.key]: e.target.value }))}
              placeholder={`Default ${fd.kind === 'pct' ? `${bpsToPercent(defaults[fd.key] as number)}%` : defaults[fd.key]}`} />
          </div>
        ))}
      </div>
      <p className="form-field__label">Expected yearly return by how far away a goal is</p>
      <div className="form-grid form-grid--3 assumptions__returns">
        {BANDS.map((b, i) => (
          <div key={b} className="form-field">
            <label className="form-field__label" htmlFor={`as-ret${i}`}>{b} %</label>
            <input id={`as-ret${i}`} className="text-input" inputMode="decimal" value={form[`ret${i}`] ?? ''} placeholder={`Default ${bpsToPercent(defReturns[i])}%`} onChange={(e) => setForm((f) => ({ ...f, [`ret${i}`]: e.target.value }))} />
          </div>
        ))}
      </div>
      {err && <div className="form-alert form-alert--error">{err}</div>}
      {save.isError && <div className="form-alert form-alert--error">{(save.error as Error).message}</div>}
      <div className="form-actions-row">
        <span className="muted assumptions__ver">Using: {String(eff.version)}</span>
        <button type="button" className="btn btn--outline" disabled={reset.isPending || Object.keys(a.overrides).length === 0} onClick={() => reset.mutate()}>Back to defaults</button>
        <button type="submit" className="btn btn--primary" disabled={save.isPending}>Save assumptions</button>
      </div>
    </form>
  );
};

export const PlanPage: React.FC = () => {
  const versions = useVersions();
  const publish = usePublishVersion();
  const list = versions.data ?? [];
  const [label, setLabel] = useState('');
  const [compare, setCompare] = useState<{ from: string; to: string | null } | null>(null);
  const [verified, setVerified] = useState<Record<string, VerifyResult>>({});
  const sinceLatest = useChanges(null, null, list.length > 0 && !compare);
  const between = useChanges(compare?.from ?? null, compare?.to ?? null, !!compare);
  const shown = compare ? between : sinceLatest;

  return (
    <div className="page-container">
      <header className="page-header-row">
        <div>
          <h1 className="page-title">Plan & history</h1>
          <p className="page-subtitle">Save a snapshot of your plan, see what changed since, and adjust the assumptions behind every number.</p>
        </div>
      </header>

      <section className="card plan-save">
        <h2 className="card__title">Save this version of your plan</h2>
        <p className="card__subtitle">A saved version is frozen: later edits never change it, and it can always be recalculated to the same numbers.</p>
        <form className="plan-save__row" onSubmit={async (e) => { e.preventDefault(); await publish.mutateAsync(label); setLabel(''); setCompare(null); }}>
          <input className="text-input" aria-label="Version name" placeholder="Name (optional), e.g. After my raise" value={label} onChange={(e) => setLabel(e.target.value)} maxLength={120} />
          <button type="submit" className="btn btn--primary" disabled={publish.isPending}>{publish.isPending ? 'Saving…' : 'Save version'}</button>
        </form>
      </section>

      <section className="card">
        <div className="numbers__head">
          <h2 className="card__title">{compare ? 'Comparing versions' : 'What changed since your last saved plan'}</h2>
          {compare && <button type="button" className="btn btn--outline btn--sm" onClick={() => setCompare(null)}>Back to “since last save”</button>}
        </div>
        {list.length === 0 && <p className="muted">Save your first version above; from then on, this shows every change and what it did to your goals.</p>}
        {shown.isLoading && list.length > 0 && <p className="muted">Comparing…</p>}
        {shown.data && <Changes d={shown.data} />}
      </section>

      {list.length > 0 && (
        <section className="card">
          <h2 className="card__title">Saved versions</h2>
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Version</th><th>Saved</th><th>Net worth</th><th>Surplus</th><th>Goals on track</th><th /></tr></thead>
              <tbody>
                {list.map((v, i) => (
                  <tr key={v.id}>
                    <td><strong>#{v.number}</strong> {v.label && <span className="muted">· {v.label}</span>}<div className="data-table__note">{v.assumptions_version}</div></td>
                    <td>{day(v.as_of)}</td>
                    <td>{inrShort(v.net_worth_paise)}</td>
                    <td>{inr(v.monthly_surplus_paise)}</td>
                    <td>{v.goals_on_track ?? 0} / {v.goals_total ?? 0}</td>
                    <td className="version-actions">
                      {i < list.length - 1 && <button type="button" className="btn-link" onClick={() => setCompare({ from: list[i + 1].id, to: v.id })}>vs #{list[i + 1].number}</button>}
                      <button type="button" className="btn-link" onClick={async () => setVerified({ ...verified, [v.id]: await verifyVersion(v.id) })}>Check</button>
                      {verified[v.id] && <Pill status={verified[v.id].reproducible ? 'good' : 'critical'} label={verified[v.id].reproducible ? 'Reproduces exactly' : 'Mismatch'} />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="card">
        <h2 className="card__title">Assumptions</h2>
        <p className="card__subtitle">These drive every projection. Leave a box empty to use the default. Changes apply everywhere straight away; see their effect above. <Link to="/goals">Check your goals</Link> after changing.</p>
        <AssumptionsEditor />
      </section>
    </div>
  );
};
