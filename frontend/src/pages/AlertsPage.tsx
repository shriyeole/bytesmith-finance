import React, { useState } from 'react';
import { useAlerts, useAlertMutations } from '../api/journey';
import { ActionCard, severityLabel } from '../features/planning/dashboard';

const ORDER = ['critical', 'warning', 'attention', 'opportunity', 'info'];

export const AlertsPage: React.FC = () => {
  const [hidden, setHidden] = useState(false);
  const q = useAlerts(hidden);
  const { done } = useAlertMutations();
  const list = q.data?.alerts ?? [];
  const open = list.filter((a) => a.status === 'open');
  const parked = list.filter((a) => a.status !== 'open');
  return (
    <div className="page-container">
      <header className="page-header-row">
        <div>
          <h1 className="page-title">Alerts</h1>
          <p className="page-subtitle">Checked against your latest numbers every time you open this page, and once a day.</p>
        </div>
        <label className="check-field"><input type="checkbox" checked={hidden} onChange={(e) => setHidden(e.target.checked)} /> Show snoozed, dismissed and done</label>
      </header>
      {q.isLoading && <p className="muted">Checking…</p>}
      {q.data && open.length === 0 && <div className="card"><p className="muted">No open alerts. Your plan has nothing that needs attention right now.</p></div>}
      {ORDER.map((sev) => {
        const items = open.filter((a) => a.severity === sev);
        if (!items.length) return null;
        return (
          <section key={sev} className="alert-group">
            <h2 className="section-heading">{severityLabel(sev)} ({items.length})</h2>
            <div className="alert-grid">{items.map((a) => <ActionCard key={a.id} a={a} />)}</div>
          </section>
        );
      })}
      {hidden && parked.length > 0 && (
        <section className="alert-group">
          <h2 className="section-heading">Parked</h2>
          <ul className="parked">
            {parked.map((a) => (
              <li key={a.id}><strong>{a.title}</strong> <span className="muted">· {a.status}{a.snoozed_until ? ` until ${a.snoozed_until}` : ''}</span>
                {a.status !== 'acted' && <button type="button" className="btn-link" onClick={() => done.mutate(a.id)}>Mark done</button>}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
};
