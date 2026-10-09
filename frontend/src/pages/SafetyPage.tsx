import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { DebtOverview, prepayLoan, PrepayScenario, useDebts, useEmergencyFund, useProtection } from '../api/planning';
import { day, duration, inr, inrShort, pct } from '../features/planning/format';
import { Method, Pill, Progress, Stat } from '../features/planning/ui';
import { rupeesToPaise } from '../utils/money';

const EmergencySection: React.FC = () => {
  const q = useEmergencyFund();
  const ef = q.data;
  if (!ef) return <section className="card"><p className="muted">{q.isError ? (q.error as Error).message : 'Loading…'}</p></section>;
  const toHigh = ef.target_high_paise ? (ef.current_paise * 10000) / ef.target_high_paise : 0;
  return (
    <section className="card safety-card">
      <div className="numbers__head"><h2 className="card__title">Emergency fund</h2><Pill status={ef.status} /></div>
      {ef.status === 'needs_info' ? <p className="muted">Add your essential spending in <Link to="/setup/expenses">My finances</Link> to size your emergency fund.</p> : (
        <>
          <p className="card__subtitle">Covers {ef.months_covered ?? 0} months of essentials. Aim for {ef.target_months_low}–{ef.target_months_high} months.</p>
          <div className="range-bar">
            <Progress bps={toHigh} tone={ef.status === 'good' ? 'good' : ef.status === 'attention' ? 'warn' : 'bad'} />
            <span className="range-bar__marker" style={{ left: `${(ef.target_months_low / ef.target_months_high) * 100}%` }} title="Minimum target" />
          </div>
          <div className="numbers__grid">
            <Stat label="You have" value={inrShort(ef.current_paise)} sub={ef.uses_flagged_assets ? 'Marked as emergency fund' : 'All cash, savings & deposits'} />
            <Stat label="Target range" value={`${inrShort(ef.target_low_paise)} – ${inrShort(ef.target_high_paise)}`} sub={`${inr(ef.monthly_obligations_paise)}/month of essentials, premiums & EMIs`} />
            <Stat label="Gap to minimum" value={inr(ef.gap_to_low_paise)} bad={ef.gap_to_low_paise > 0} sub={ef.gap_to_low_paise ? `${inr(ef.monthly_to_reach_low_in_12m_paise)}/month closes it in a year` : 'Covered'} />
          </div>
          <Method lines={[...ef.reasons, ...ef.method]} title="Why this range" />
        </>
      )}
    </section>
  );
};

const PrepayTool: React.FC<{ loans: DebtOverview['loans'] }> = ({ loans }) => {
  const eligible = loans.filter((l) => l.interest_rate_bps !== null && l.interest_rate_bps !== undefined && l.emi_paise > 0 && l.months_left);
  const [loanId, setLoanId] = useState(eligible[0]?.id ?? '');
  const [lump, setLump] = useState('');
  const [extra, setExtra] = useState('');
  const [res, setRes] = useState<PrepayScenario | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (!eligible.length) return null;
  const run = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setErr(null);
    try {
      setRes(await prepayLoan(loanId || eligible[0].id, { lump_sum_paise: rupeesToPaise(lump) ?? 0, extra_monthly_paise: rupeesToPaise(extra) ?? 0 }));
    } catch (e) {
      setErr((e as Error).message);
      setRes(null);
    }
  };
  const verdict = res && (res.better_option === 'prepay' ? 'Prepaying comes out ahead' : res.better_option === 'invest' ? 'Investing comes out ahead (if returns hold)' : 'Both come out about the same');
  return (
    <form className="prepay" onSubmit={run}>
      <h3 className="sub-section__title">Prepay or invest?</h3>
      <div className="form-grid form-grid--3">
        <div className="form-field"><label className="form-field__label" htmlFor="pp-loan">Loan</label>
          <select id="pp-loan" className="text-input" value={loanId} onChange={(e) => setLoanId(e.target.value)}>
            {eligible.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select></div>
        <div className="form-field"><label className="form-field__label" htmlFor="pp-lump">One-time prepayment</label>
          <div className="currency-input-wrapper"><span className="currency-input-prefix">₹</span><input id="pp-lump" className="currency-input" inputMode="decimal" value={lump} placeholder="0" onChange={(e) => setLump(e.target.value)} /></div></div>
        <div className="form-field"><label className="form-field__label" htmlFor="pp-extra">Extra every month</label>
          <div className="currency-input-wrapper"><span className="currency-input-prefix">₹</span><input id="pp-extra" className="currency-input" inputMode="decimal" value={extra} placeholder="0" onChange={(e) => setExtra(e.target.value)} /></div></div>
      </div>
      <div className="form-actions-row"><button type="submit" className="btn btn--primary">Compare</button></div>
      {err && <div className="form-alert form-alert--error">{err}</div>}
      {res && (
        <div className="prepay__result">
          <p className="prepay__verdict">{verdict}</p>
          <div className="numbers__grid">
            <Stat label="Loan ends" value={`${duration(res.months_saved)} sooner`} sub={`${duration(res.new_months)} instead of ${duration(res.base_months)}`} />
            <Stat label="Interest saved" value={inr(res.interest_saved_paise)} sub="Guaranteed" />
            <Stat label="Wealth if you prepay" value={inrShort(res.wealth_if_prepay_paise)} sub="On the original end date" />
            <Stat label="Wealth if you invest" value={inrShort(res.wealth_if_invest_paise)} sub={`Assumes ${pct(res.investment_return_bps)} a year`} />
          </div>
          <Method lines={res.explanation} title="How this compares" />
        </div>
      )}
    </form>
  );
};

const DebtSection: React.FC = () => {
  const q = useDebts();
  const d = q.data;
  if (!d) return <section className="card"><p className="muted">{q.isError ? (q.error as Error).message : 'Loading…'}</p></section>;
  const byId = new Map(d.loans.map((l) => [l.id, l]));
  return (
    <section className="card safety-card">
      <div className="numbers__head"><h2 className="card__title">Loans</h2><Pill status={d.status} /></div>
      {d.status === 'none' ? <p className="muted">No loans recorded. <Link to="/setup/loans">Add one</Link> if you have any.</p> : (
        <>
          <div className="numbers__grid">
            <Stat label="Total owed" value={inrShort(d.total_outstanding_paise)} />
            <Stat label="EMIs per month" value={inr(d.total_emi_paise)} sub={`${pct(d.debt_to_income_bps)} of take-home pay`} />
            <Stat label="High-cost debt" value={inrShort(d.high_cost_outstanding_paise)} bad={d.high_cost_outstanding_paise > 0} />
          </div>
          {d.messages.map((m) => <p key={m} className="callout-box__sub">{m}</p>)}
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>Pay off order</th><th>Owed</th><th>Rate</th><th>EMI</th><th>Ends</th><th>Interest left</th></tr></thead>
              <tbody>
                {d.payoff_order.map((lid, i) => {
                  const l = byId.get(lid)!;
                  return (
                    <tr key={lid}>
                      <td><strong>{i + 1}. {l.name}</strong>{l.high_cost && <span className="pill pill--bad pill--inline">High cost</span>}{l.notes.map((n) => <div key={n} className="data-table__note">{n}</div>)}</td>
                      <td>{inr(l.outstanding_paise)}</td>
                      <td>{pct(l.interest_rate_bps)}</td>
                      <td>{inr(l.emi_paise)}</td>
                      <td>{l.payoff_date ? day(l.payoff_date) : '—'}</td>
                      <td>{l.interest_remaining_paise === null || l.interest_remaining_paise === undefined ? '—' : inr(l.interest_remaining_paise)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <PrepayTool loans={d.loans} />
          <Method lines={d.method} />
        </>
      )}
    </section>
  );
};

const ProtectionSection: React.FC = () => {
  const q = useProtection();
  const p = q.data;
  if (!p) return <section className="card"><p className="muted">{q.isError ? (q.error as Error).message : 'Loading…'}</p></section>;
  const Cover: React.FC<{ title: string; c: typeof p.life }> = ({ title, c }) => (
    <div className="cover">
      <div className="numbers__head"><h3 className="sub-section__title">{title}</h3><Pill status={c.status} /></div>
      <div className="numbers__grid">
        <Stat label="Suggested" value={inrShort(c.recommended_paise)} />
        <Stat label="You have" value={inrShort(c.existing_paise)} />
        <Stat label="Gap" value={inrShort(c.gap_paise)} bad={c.gap_paise > 0} />
      </div>
      <Method lines={c.reasons} title="How we estimated this" />
    </div>
  );
  return (
    <section className="card safety-card">
      <h2 className="card__title">Insurance</h2>
      <Cover title="Life cover" c={p.life} />
      <Cover title="Health cover" c={p.health} />
      {p.messages.map((m) => <div key={m} className="callout-box callout-box--neutral"><div className="callout-box__content"><p className="callout-box__sub">{m}</p></div></div>)}
      <Method lines={p.method} title="About these numbers" />
    </section>
  );
};

export const SafetyPage: React.FC = () => (
  <div className="page-container">
    <header className="page-header-row">
      <div>
        <h1 className="page-title">Safety net</h1>
        <p className="page-subtitle">Cash for emergencies, loans under control and the right insurance come before investing.</p>
      </div>
    </header>
    <EmergencySection />
    <DebtSection />
    <ProtectionSection />
  </div>
);
