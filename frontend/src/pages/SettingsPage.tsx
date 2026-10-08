import React, { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useDeleteAccount, useMe } from '../api/financialState';
import { useAuth } from '../auth/AuthContext';

export const SettingsPage: React.FC = () => {
  const me = useMe();
  const auth = useAuth();
  const qc = useQueryClient();
  const del = useDeleteAccount();
  const [confirm, setConfirm] = useState('');

  const deleteAll = async () => {
    await del.mutateAsync();
    qc.clear();
    await auth.signOut();
  };

  return (
    <div className="page-container">
      <header className="page-header-row"><div><h1 className="page-title">Account</h1></div></header>
      <section className="card">
        <h2 className="card__title">Signed in as</h2>
        <p>{me.data?.email ?? me.data?.display_name ?? me.data?.id ?? '…'}</p>
        <div className="form-actions-row"><button type="button" className="btn btn--outline" onClick={() => { qc.clear(); auth.signOut(); }}>Sign out</button></div>
      </section>
      <section className="card danger-zone">
        <h2 className="card__title">Delete account and data</h2>
        <p className="muted">Permanently removes your profile, income, spending, assets, loans, insurance and goals. This cannot be undone.</p>
        <div className="form-field">
          <label className="form-field__label" htmlFor="confirm-delete">Type DELETE to confirm</label>
          <input id="confirm-delete" className="text-input" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </div>
        <button type="button" className="btn btn--danger" disabled={confirm !== 'DELETE' || del.isPending} onClick={deleteAll}>{del.isPending ? 'Deleting…' : 'Delete everything'}</button>
        {del.isError && <div className="form-alert form-alert--error">{(del.error as Error).message}</div>}
      </section>
    </div>
  );
};
