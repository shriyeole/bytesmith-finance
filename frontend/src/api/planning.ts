/** Typed API + React Query hooks for M4 planning. */

import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { components } from './schema';
import { apiFetch } from './http';

type S = components['schemas'];
export type Goal = S['GoalRead'];
export type GoalCreate = S['GoalCreate'];
export type GoalUpdate = S['GoalUpdate'];
export type GoalWhatIf = S['GoalWhatIf'];
export type GoalEvaluation = S['GoalEvaluation'];
export type GoalsPlan = S['GoalsPlan'];
export type EmergencyFund = S['EmergencyFund'];
export type DebtOverview = S['DebtOverview'];
export type PrepayScenario = S['PrepayScenario'];
export type Protection = S['Protection'];
export type PlanOverview = S['PlanOverview'];

export const planKeys = {
  all: ['plan'] as const,
  goalsPlan: ['plan', 'goals'] as const,
  goal: (id: string) => ['plan', 'goal', id] as const,
  evaluation: (id: string) => ['plan', 'evaluation', id] as const,
  emergency: ['plan', 'emergency'] as const,
  debts: ['plan', 'debts'] as const,
  protection: ['plan', 'protection'] as const,
  overview: ['plan', 'overview'] as const,
};

export const useGoalsPlan = () => useQuery({ queryKey: planKeys.goalsPlan, queryFn: () => apiFetch<GoalsPlan>('/plan/goals') });
export const useGoals = () => useQuery({ queryKey: ['plan', 'goal-list'], queryFn: () => apiFetch<Goal[]>('/goals') });
export const useGoal = (id: string | undefined) =>
  useQuery({ queryKey: planKeys.goal(id ?? ''), queryFn: () => apiFetch<Goal>(`/goals/${id}`), enabled: !!id });
export const useGoalEvaluation = (id: string | undefined) =>
  useQuery({ queryKey: planKeys.evaluation(id ?? ''), queryFn: () => apiFetch<GoalEvaluation>(`/goals/${id}/evaluation`), enabled: !!id });
export const useEmergencyFund = () => useQuery({ queryKey: planKeys.emergency, queryFn: () => apiFetch<EmergencyFund>('/plan/emergency-fund') });
export const useDebts = () => useQuery({ queryKey: planKeys.debts, queryFn: () => apiFetch<DebtOverview>('/plan/debts') });
export const useProtection = () => useQuery({ queryKey: planKeys.protection, queryFn: () => apiFetch<Protection>('/plan/protection') });
export const usePlanOverview = () => useQuery({ queryKey: planKeys.overview, queryFn: () => apiFetch<PlanOverview>('/plan/overview') });

export function useGoalMutations() {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: planKeys.all });
  return {
    create: useMutation({
      mutationFn: (body: GoalCreate) => apiFetch<Goal>('/goals', { method: 'POST', body: JSON.stringify(body) }),
      onSuccess: refresh,
    }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: string; body: GoalUpdate }) =>
        apiFetch<Goal>(`/goals/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
      onSuccess: refresh,
    }),
    remove: useMutation({ mutationFn: (id: string) => apiFetch<void>(`/goals/${id}`, { method: 'DELETE' }), onSuccess: refresh }),
  };
}

export const previewGoal = (body: GoalCreate) =>
  apiFetch<GoalEvaluation>('/goals/preview', { method: 'POST', body: JSON.stringify(body) });
export const whatIfGoal = (id: string, body: GoalWhatIf) =>
  apiFetch<GoalEvaluation>(`/goals/${id}/what-if`, { method: 'POST', body: JSON.stringify(body) });
export const prepayLoan = (id: string, body: { lump_sum_paise: number; extra_monthly_paise: number }) =>
  apiFetch<PrepayScenario>(`/plan/debts/${id}/prepay`, { method: 'POST', body: JSON.stringify(body) });

/** Value that only updates after `ms` without changes (for live previews). */
export function useDebounced<T>(value: T, ms = 350): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}
