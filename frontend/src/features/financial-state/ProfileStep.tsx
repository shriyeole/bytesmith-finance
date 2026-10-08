import React, { useEffect, useState } from 'react';
import { HouseholdProfileUpdate, useHousehold, useSaveHousehold } from '../../api/financialState';
import { FieldDef, FieldInput, ItemsStep } from './ItemsStep';
import { L, labelOf } from './labels';

const profileFields: FieldDef[] = [
  { name: 'full_name', label: 'Your name', kind: 'text' },
  { name: 'date_of_birth', label: 'Date of birth', kind: 'date', required: true },
  { name: 'retirement_age', label: 'Age you want to retire at', kind: 'integer', required: true, placeholder: 'e.g. 60' },
  { name: 'employment_type', label: 'Work', kind: 'select', options: L.employment, required: true },
  { name: 'income_stability', label: 'How steady is your income?', kind: 'select', options: L.stability },
  { name: 'marital_status', label: 'Marital status', kind: 'select', options: L.marital },
  { name: 'tax_regime', label: 'Income-tax regime', kind: 'select', options: L.taxRegime },
  { name: 'city', label: 'City', kind: 'text' },
];

const memberFields: FieldDef[] = [
  { name: 'name', label: 'Name', kind: 'text', required: true },
  { name: 'relationship', label: 'Relationship', kind: 'select', options: L.relationship, required: true },
  { name: 'date_of_birth', label: 'Date of birth', kind: 'date' },
  { name: 'is_dependent', label: 'Depends on my income', kind: 'checkbox', defaultValue: true },
];

type Form = Record<string, string | boolean>;

export const ProfileStep: React.FC<{ onSaved: () => void }> = ({ onSaved }) => {
  const household = useHousehold();
  const save = useSaveHousehold();
  const [form, setForm] = useState<Form>(() => Object.fromEntries(profileFields.map((f) => [f.name, ''])));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (household.data) {
      const d = household.data as unknown as Record<string, unknown>;
      setForm(Object.fromEntries(profileFields.map((f) => [f.name, d[f.name] == null ? '' : String(d[f.name])])));
    }
  }, [household.data]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const missing = profileFields.filter((f) => f.required && String(form[f.name]).trim() === '');
    if (missing.length) {
      setError(`Please fill: ${missing.map((f) => f.label).join(', ')}`);
      return;
    }
    const age = String(form.retirement_age).trim();
    if (!/^\d+$/.test(age)) {
      setError('Retirement age must be a whole number');
      return;
    }
    const body: Record<string, unknown> = {};
    for (const f of profileFields) {
      const v = String(form[f.name]).trim();
      body[f.name] = v === '' ? null : f.name === 'retirement_age' ? Number(v) : v;
    }
    try {
      await save.mutateAsync(body as HouseholdProfileUpdate);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <>
      <form className="card item-form" onSubmit={submit} noValidate>
        <div className="form-grid form-grid--2">
          {profileFields.map((f) => (
            <FieldInput key={f.name} idPrefix="profile" field={f} value={form[f.name]} onChange={(v) => setForm((s) => ({ ...s, [f.name]: v }))} />
          ))}
        </div>
        {error && <div className="form-alert form-alert--error" role="alert">{error}</div>}
        <div className="form-actions-row">
          <button type="submit" className="btn btn--primary" disabled={save.isPending}>{save.isPending ? 'Saving…' : 'Save & continue'}</button>
        </div>
      </form>

      <section className="sub-section">
        <h3 className="sub-section__title">Family members</h3>
        <p className="muted">Add your spouse, children or parents, especially anyone who depends on your income. Optional.</p>
        <ItemsStep collection="household/members" noun="family member" fields={memberFields} emptyText="No family members added." collapsedWhenEmpty
          describe={(m) => ({ title: String(m.name), detail: `${labelOf(L.relationship, m.relationship as string)}${m.is_dependent ? ' · dependent' : ''}` })} />
      </section>
    </>
  );
};
