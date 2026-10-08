import React from 'react';
import type { OnboardingStep } from '../../api/financialState';
import { formatINR } from '../../utils/currency';
import { bpsToPercent } from '../../utils/money';
import { FieldDef, ItemsStep } from './ItemsStep';
import { L, labelOf } from './labels';

type Item = Record<string, unknown> & { id: string };
const money = (v: unknown) => formatINR(v as number);
const freq = (v: unknown) => (v === 'monthly' ? '/month' : ` ${labelOf(L.frequency, v as string).toLowerCase()}`);

const incomeFields: FieldDef[] = [
  { name: 'name', label: 'Name', kind: 'text', required: true, placeholder: 'e.g. Salary' },
  { name: 'kind', label: 'Type', kind: 'select', options: L.incomeKind, required: true, defaultValue: 'salary' },
  { name: 'amount_paise', label: 'Amount (take-home)', kind: 'money', required: true },
  { name: 'frequency', label: 'How often', kind: 'select', options: L.frequency, required: true, defaultValue: 'monthly' },
  { name: 'owner', label: 'Earned by', kind: 'select', options: L.owner, required: true, defaultValue: 'self' },
  { name: 'expected_growth_bps', label: 'Expected yearly growth %', kind: 'percent', allowNegative: true, help: 'Your best guess for raises. Leave blank if unsure.' },
];

const expenseFields: FieldDef[] = [
  { name: 'name', label: 'Name', kind: 'text', required: true, placeholder: 'e.g. Rent' },
  { name: 'category', label: 'Category', kind: 'select', options: L.expenseCategory, required: true },
  { name: 'amount_paise', label: 'Amount', kind: 'money', required: true },
  { name: 'frequency', label: 'How often', kind: 'select', options: L.frequency, required: true, defaultValue: 'monthly' },
  { name: 'bucket', label: 'Essential or discretionary?', kind: 'select', options: L.bucket, blankLabel: 'Decide from category', help: 'Essential = must pay even in a bad month.' },
];

const assetFields: FieldDef[] = [
  { name: 'name', label: 'Name', kind: 'text', required: true, placeholder: 'e.g. HDFC savings' },
  { name: 'asset_type', label: 'Type', kind: 'select', options: L.assetType, required: true },
  { name: 'current_value_paise', label: 'Current value', kind: 'money', required: true },
  { name: 'monthly_contribution_paise', label: 'Monthly investment into it (SIP etc.)', kind: 'money', placeholder: '0' },
  { name: 'owner', label: 'Owned by', kind: 'select', options: L.owner, required: true, defaultValue: 'self' },
  { name: 'liquidity', label: 'How quickly can you use it?', kind: 'select', options: L.liquidity, blankLabel: 'Decide from type' },
  { name: 'is_emergency_fund', label: 'This is my emergency fund', kind: 'checkbox' },
];

const liabilityFields: FieldDef[] = [
  { name: 'name', label: 'Name', kind: 'text', required: true, placeholder: 'e.g. Car loan' },
  { name: 'liability_type', label: 'Type', kind: 'select', options: L.liabilityType, required: true },
  { name: 'outstanding_paise', label: 'Amount still owed', kind: 'money', required: true },
  { name: 'emi_paise', label: 'Monthly EMI', kind: 'money', placeholder: '0' },
  { name: 'interest_rate_bps', label: 'Interest rate % per year', kind: 'percent' },
  { name: 'remaining_months', label: 'Months left', kind: 'integer' },
  { name: 'lender', label: 'Lender', kind: 'text' },
];

const policyFields: FieldDef[] = [
  { name: 'policy_type', label: 'Type', kind: 'select', options: L.policyType, required: true },
  { name: 'cover_amount_paise', label: 'Cover amount', kind: 'money', required: true },
  { name: 'annual_premium_paise', label: 'Yearly premium you pay', kind: 'money', placeholder: '0' },
  { name: 'source', label: 'Source', kind: 'select', options: L.coverSource, required: true, defaultValue: 'personal' },
  { name: 'covers', label: 'Who is covered', kind: 'text', defaultValue: 'self', placeholder: 'self / family / spouse' },
  { name: 'provider', label: 'Insurer', kind: 'text' },
  { name: 'renewal_date', label: 'Renewal date', kind: 'date' },
];

export interface StepDef {
  step: OnboardingStep;
  path: string;
  title: string;
  intro: string;
  noneLabel?: string;
  body: React.ReactNode;
}

export const ITEM_STEPS: StepDef[] = [
  {
    step: 'income', path: 'income', title: 'Income',
    intro: 'Add what reaches your bank account after tax. Include your partner if you plan together.',
    body: (
      <ItemsStep collection="incomes" noun="income" fields={incomeFields} emptyText="No income added yet."
        describe={(i: Item) => ({ title: String(i.name), detail: `${labelOf(L.incomeKind, i.kind as string)} · ${labelOf(L.owner, i.owner as string)}${i.expected_growth_bps != null ? ` · grows ${bpsToPercent(i.expected_growth_bps as number)}%/yr` : ''}`, amount: `${money(i.amount_paise)}${freq(i.frequency)}` })} />
    ),
  },
  {
    step: 'expenses', path: 'expenses', title: 'Spending',
    intro: 'Rough monthly figures are fine. Leave out loan EMIs and insurance premiums; they come in later steps.',
    body: (
      <ItemsStep collection="expenses" noun="expense" fields={expenseFields} emptyText="No spending added yet."
        describe={(i: Item) => ({ title: String(i.name), detail: `${labelOf(L.expenseCategory, i.category as string)} · ${labelOf(L.bucket, i.bucket as string)}`, amount: `${money(i.amount_paise)}${freq(i.frequency)}` })} />
    ),
  },
  {
    step: 'assets', path: 'assets', title: 'Savings & investments',
    intro: 'Bank balances, deposits, funds, retirement accounts, gold and property. Current value is enough.',
    noneLabel: 'I have no savings yet',
    body: (
      <ItemsStep collection="assets" noun="asset" fields={assetFields} emptyText="No assets added yet."
        describe={(i: Item) => ({ title: `${i.name}${i.is_emergency_fund ? ' · emergency fund' : ''}`, detail: `${labelOf(L.assetType, i.asset_type as string)} · ${labelOf(L.liquidity, i.liquidity as string)}${(i.monthly_contribution_paise as number) > 0 ? ` · +${money(i.monthly_contribution_paise)}/month` : ''}`, amount: money(i.current_value_paise) })} />
    ),
  },
  {
    step: 'liabilities', path: 'loans', title: 'Loans & credit cards',
    intro: 'Anything you still owe. The EMI is counted in your monthly outgoings automatically.',
    noneLabel: 'I have no loans',
    body: (
      <ItemsStep collection="liabilities" noun="loan" fields={liabilityFields} emptyText="No loans added."
        describe={(i: Item) => ({ title: String(i.name), detail: `${labelOf(L.liabilityType, i.liability_type as string)}${i.interest_rate_bps != null ? ` · ${bpsToPercent(i.interest_rate_bps as number)}%` : ''}${(i.emi_paise as number) > 0 ? ` · EMI ${money(i.emi_paise)}` : ''}`, amount: money(i.outstanding_paise) })} />
    ),
  },
  {
    step: 'insurance', path: 'insurance', title: 'Insurance',
    intro: 'Health and life cover, including what your employer provides.',
    noneLabel: 'I have no insurance',
    body: (
      <ItemsStep collection="insurance" noun="policy" fields={policyFields} emptyText="No policies added."
        describe={(i: Item) => ({ title: labelOf(L.policyType, i.policy_type as string), detail: `${labelOf(L.coverSource, i.source as string)} · covers ${i.covers}${i.provider ? ` · ${i.provider}` : ''}`, amount: money(i.cover_amount_paise) })} />
    ),
  },
];
