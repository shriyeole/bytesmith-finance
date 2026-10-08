/** Human labels for API enum values. Keys must match the backend enums. */

export type Option = { value: string; label: string };
const opts = (o: Record<string, string>): Option[] => Object.entries(o).map(([value, label]) => ({ value, label }));

export const L = {
  marital: opts({ single: 'Single', married: 'Married', divorced: 'Divorced', widowed: 'Widowed' }),
  employment: opts({ salaried: 'Salaried', self_employed: 'Self-employed', business_owner: 'Business owner', freelancer: 'Freelancer', not_working: 'Not working', retired: 'Retired' }),
  stability: opts({ stable: 'Stable — fixed salary', variable: 'Variable — bonus / commission heavy', uncertain: 'Uncertain — irregular income' }),
  taxRegime: opts({ new: 'New regime', old: 'Old regime', unknown: "Don't know" }),
  relationship: opts({ spouse: 'Spouse', child: 'Child', parent: 'Parent', sibling: 'Sibling', other: 'Other' }),
  frequency: opts({ monthly: 'Monthly', quarterly: 'Quarterly', half_yearly: 'Every 6 months', yearly: 'Yearly', one_time: 'One-time' }),
  owner: opts({ self: 'Me', spouse: 'Spouse', joint: 'Joint', other: 'Other' }),
  incomeKind: opts({ salary: 'Salary', bonus: 'Bonus / variable pay', business: 'Business income', freelance: 'Freelance', rental: 'Rent received', interest_dividend: 'Interest / dividends', pension: 'Pension', other: 'Other' }),
  expenseCategory: opts({
    housing: 'Rent / housing', groceries: 'Groceries', utilities: 'Utilities & bills', transport: 'Transport / fuel',
    healthcare: 'Healthcare', children: 'Children (school, care)', education: 'Own education', family_support: 'Family support',
    household_help: 'Household help', dining: 'Eating out', shopping: 'Shopping', travel: 'Travel & holidays',
    entertainment: 'Entertainment', subscriptions: 'Subscriptions', personal_care: 'Personal care',
    gifts_donations: 'Gifts & donations', other: 'Other',
  }),
  bucket: opts({ essential: 'Essential', discretionary: 'Discretionary' }),
  assetType: opts({
    savings_account: 'Savings account', cash: 'Cash', fixed_deposit: 'Fixed deposit', mutual_fund: 'Mutual funds',
    direct_equity: 'Stocks', epf: 'EPF', ppf: 'PPF', nps: 'NPS', gold: 'Gold', real_estate: 'Property',
    business: 'Business ownership', other: 'Other',
  }),
  liquidity: opts({ immediate: 'Usable today', short_term: 'Within days', market_linked: 'Sellable (value moves)', locked: 'Locked in', illiquid: 'Hard to sell' }),
  liabilityType: opts({ home_loan: 'Home loan', car_loan: 'Car loan', personal_loan: 'Personal loan', education_loan: 'Education loan', credit_card: 'Credit card balance', gold_loan: 'Gold loan', other: 'Other loan' }),
  policyType: opts({ health: 'Health insurance', term_life: 'Term life', other_life: 'Other life (endowment/ULIP)', critical_illness: 'Critical illness', personal_accident: 'Personal accident', disability: 'Disability' }),
  coverSource: opts({ personal: 'Bought myself', employer: 'From employer' }),
};

export function labelOf(options: Option[], value: string | null | undefined): string {
  return options.find((o) => o.value === value)?.label ?? value ?? '—';
}
