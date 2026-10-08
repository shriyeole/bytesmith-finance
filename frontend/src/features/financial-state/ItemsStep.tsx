/**
 * Generic "list + add/edit form" step used for income, expenses, assets, loans and insurance.
 * Field definitions drive both the form and the request payload.
 */

import React, { useState } from 'react';
import { Collection, useCollection, useCollectionMutations } from '../../api/financialState';
import { ClientError } from '../../api/http';
import { bpsToPercent, paiseToRupees, percentToBps, rupeesToPaise } from '../../utils/money';
import { Option } from './labels';

export type FieldKind = 'text' | 'money' | 'percent' | 'select' | 'date' | 'checkbox' | 'integer';

export interface FieldDef {
  name: string;
  label: string;
  kind: FieldKind;
  options?: Option[];
  required?: boolean;
  help?: string;
  placeholder?: string;
  defaultValue?: string | boolean;
  allowNegative?: boolean;
  /** Leave blank to let the server choose (e.g. bucket from category). */
  blankLabel?: string;
}

type FormState = Record<string, string | boolean>;
type Item = Record<string, unknown> & { id: string };

function emptyForm(fields: FieldDef[]): FormState {
  return Object.fromEntries(fields.map((f) => [f.name, f.defaultValue ?? (f.kind === 'checkbox' ? false : '')]));
}

function fromItem(fields: FieldDef[], item: Item): FormState {
  const s: FormState = {};
  for (const f of fields) {
    const v = item[f.name];
    if (f.kind === 'checkbox') s[f.name] = Boolean(v);
    else if (f.kind === 'money') s[f.name] = paiseToRupees(v as number | null);
    else if (f.kind === 'percent') s[f.name] = bpsToPercent(v as number | null);
    else s[f.name] = v === null || v === undefined ? '' : String(v);
  }
  return s;
}

function toPayload(fields: FieldDef[], form: FormState, isEdit: boolean): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    const raw = form[f.name] ?? '';
    if (f.kind === 'checkbox') {
      out[f.name] = Boolean(raw);
      continue;
    }
    const text = String(raw).trim();
    let value: unknown;
    try {
      if (f.kind === 'money') value = rupeesToPaise(text);
      else if (f.kind === 'percent') value = percentToBps(text, f.allowNegative);
      else if (f.kind === 'integer') {
        if (text !== '' && !/^\d+$/.test(text)) throw new Error('Enter a whole number');
        value = text === '' ? null : Number(text);
      } else value = text === '' ? null : text;
    } catch (e) {
      throw new Error(`${f.label}: ${(e as Error).message}`);
    }
    if (value === null) {
      if (f.required) throw new Error(`${f.label} is required`);
      // On create, omit blanks so server defaults apply; on edit, send null to clear.
      if (!isEdit || f.blankLabel) continue;
    }
    out[f.name] = value;
  }
  return out;
}

export const FieldInput: React.FC<{ field: FieldDef; value: string | boolean; onChange: (v: string | boolean) => void; idPrefix: string }> = ({ field, value, onChange, idPrefix }) => {
  const id = `${idPrefix}-${field.name}`;
  if (field.kind === 'checkbox') {
    return (
      <label className="check-field" htmlFor={id}>
        <input id={id} type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
        <span>{field.label}</span>
        {field.help && <small className="form-field__helper">{field.help}</small>}
      </label>
    );
  }
  return (
    <div className="form-field">
      <label htmlFor={id} className="form-field__label">
        {field.label}
        {field.required && <span className="form-field__required" aria-hidden="true">*</span>}
      </label>
      {field.kind === 'select' ? (
        <select id={id} className="text-input" value={String(value)} onChange={(e) => onChange(e.target.value)}>
          {!field.required && <option value="">{field.blankLabel ?? '—'}</option>}
          {field.required && value === '' && <option value="" disabled>Select…</option>}
          {field.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      ) : field.kind === 'money' ? (
        <div className="currency-input-wrapper">
          <span className="currency-input-prefix" aria-hidden="true">₹</span>
          <input id={id} className="currency-input" inputMode="decimal" value={String(value)} placeholder={field.placeholder ?? '0'} onChange={(e) => onChange(e.target.value)} />
        </div>
      ) : (
        <input
          id={id}
          className="text-input"
          type={field.kind === 'date' ? 'date' : 'text'}
          inputMode={field.kind === 'percent' ? 'decimal' : field.kind === 'integer' ? 'numeric' : undefined}
          value={String(value)}
          placeholder={field.placeholder ?? (field.kind === 'percent' ? 'e.g. 8.5' : undefined)}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {field.help && <p className="form-field__helper">{field.help}</p>}
    </div>
  );
};

interface ItemsStepProps {
  collection: Collection;
  noun: string;
  fields: FieldDef[];
  describe: (item: Item) => { title: string; detail: string; amount?: string };
  emptyText: string;
  /** Optional sections start with the form closed even when the list is empty. */
  collapsedWhenEmpty?: boolean;
}

export const ItemsStep: React.FC<ItemsStepProps> = ({ collection, noun, fields, describe, emptyText, collapsedWhenEmpty = false }) => {
  const list = useCollection<Item>(collection);
  const { create, update, remove } = useCollectionMutations(collection);
  const [form, setForm] = useState<FormState>(() => emptyForm(fields));
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const busy = create.isPending || update.isPending;
  const reset = () => {
    setForm(emptyForm(fields));
    setEditingId(null);
    setError(null);
    setOpen(false);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const body = toPayload(fields, form, editingId !== null);
      if (editingId) await update.mutateAsync({ id: editingId, body });
      else await create.mutateAsync(body);
      reset();
    } catch (err) {
      setError(err instanceof ClientError || err instanceof Error ? err.message : 'Could not save');
    }
  };

  const items = list.data ?? [];
  const showForm = open || editingId !== null || (!collapsedWhenEmpty && list.isSuccess && items.length === 0);

  return (
    <div className="items-step">
      {list.isLoading && <p className="muted">Loading…</p>}
      {list.isError && <div className="form-alert form-alert--error">{(list.error as Error).message}</div>}

      {items.length > 0 && (
        <ul className="item-list">
          {items.map((item) => {
            const d = describe(item);
            return (
              <li key={item.id} className="item-row">
                <div className="item-row__main">
                  <span className="item-row__title">{d.title}</span>
                  <span className="item-row__detail">{d.detail}</span>
                </div>
                {d.amount && <span className="item-row__amount">{d.amount}</span>}
                <div className="item-row__actions">
                  <button type="button" className="btn-link" onClick={() => { setEditingId(item.id); setForm(fromItem(fields, item)); setOpen(true); }}>Edit</button>
                  <button type="button" className="btn-link btn-link--danger" disabled={remove.isPending} onClick={() => remove.mutate(item.id)}>Remove</button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {list.isSuccess && items.length === 0 && <p className="muted">{emptyText}</p>}

      {showForm ? (
        <form className="card item-form" onSubmit={submit} noValidate>
          <h3 className="item-form__title">{editingId ? `Edit ${noun}` : `Add ${noun}`}</h3>
          <div className="form-grid form-grid--2">
            {fields.map((f) => (
              <FieldInput key={f.name} idPrefix={collection} field={f} value={form[f.name]} onChange={(v) => setForm((s) => ({ ...s, [f.name]: v }))} />
            ))}
          </div>
          {error && <div className="form-alert form-alert--error" role="alert">{error}</div>}
          <div className="form-actions-row">
            {(items.length > 0 || editingId) && <button type="button" className="btn btn--outline" onClick={reset}>Cancel</button>}
            <button type="submit" className="btn btn--primary" disabled={busy}>{busy ? 'Saving…' : editingId ? 'Save changes' : `Add ${noun}`}</button>
          </div>
        </form>
      ) : (
        <button type="button" className="btn btn--outline" onClick={() => setOpen(true)}>+ Add {items.length ? 'another ' : ''}{noun}</button>
      )}
    </div>
  );
};
