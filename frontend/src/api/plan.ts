/** Hooks for M5 budget rules, M6 risk & allocation, M7 assumptions and plan versions. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { components } from './schema';
import { apiFetch } from './http';

type S = components['schemas'];
export type BudgetComparison = S['BudgetComparison'];
export type RuleResult = S['RuleResult'];
export type Split = S['Split'];
export type RiskQuestion = S['RiskQuestion'];
export type AllocationView = S['AllocationView'];
export type AssumptionsView = S['AssumptionsView'];
export type VersionSummary = S['VersionSummary'];
export type PlanDiff = S['PlanDiff'];
export type VerifyResult = S['VerifyResult'];

const useRefreshPlan = () => {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ['plan'] });
};

export const useFeatures = () =>
  useQuery({ queryKey: ['plan', 'features'], queryFn: () => apiFetch<{ allocation: boolean }>('/features'), staleTime: 5 * 60_000 });

export const useBudget = () => useQuery({ queryKey: ['plan', 'budget'], queryFn: () => apiFetch<BudgetComparison>('/plan/budget') });
export function useChooseBudget() {
  const refresh = useRefreshPlan();
  return useMutation({
    mutationFn: (body: { rule?: string | null; custom_savings_bps?: number | null; custom_wants_bps?: number | null }) =>
      apiFetch<BudgetComparison>('/plan/budget', { method: 'PUT', body: JSON.stringify(body) }),
    onSuccess: refresh,
  });
}

export const useRiskQuestions = (enabled: boolean) =>
  useQuery({ queryKey: ['plan', 'risk-questions'], queryFn: () => apiFetch<RiskQuestion[]>('/plan/risk-questions'), enabled, staleTime: Infinity });
export const useAllocation = (enabled: boolean) =>
  useQuery({ queryKey: ['plan', 'allocation'], queryFn: () => apiFetch<AllocationView>('/plan/allocation'), enabled });
export function useSaveRiskAnswers() {
  const refresh = useRefreshPlan();
  return useMutation({
    mutationFn: (answers: Record<string, string>) => apiFetch<AllocationView>('/plan/risk-answers', { method: 'PUT', body: JSON.stringify(answers) }),
    onSuccess: refresh,
  });
}

export const useAssumptions = () => useQuery({ queryKey: ['plan', 'assumptions'], queryFn: () => apiFetch<AssumptionsView>('/assumptions') });
export function useSaveAssumptions() {
  const refresh = useRefreshPlan();
  return {
    save: useMutation({
      mutationFn: (changes: Record<string, number | number[] | null>) => apiFetch<AssumptionsView>('/assumptions', { method: 'PUT', body: JSON.stringify(changes) }),
      onSuccess: refresh,
    }),
    reset: useMutation({ mutationFn: () => apiFetch<AssumptionsView>('/assumptions', { method: 'DELETE' }), onSuccess: refresh }),
  };
}

export const useVersions = () => useQuery({ queryKey: ['plan', 'versions'], queryFn: () => apiFetch<VersionSummary[]>('/plan/versions') });
export function usePublishVersion() {
  const refresh = useRefreshPlan();
  return useMutation({
    mutationFn: (label: string) => apiFetch<VersionSummary>('/plan/versions', { method: 'POST', body: JSON.stringify({ label: label || null }) }),
    onSuccess: refresh,
  });
}
export const useChanges = (fromId: string | null, toId: string | null, enabled: boolean) =>
  useQuery({
    queryKey: ['plan', 'changes', fromId, toId],
    queryFn: () => {
      const q = new URLSearchParams();
      if (fromId) q.set('from_id', fromId);
      if (toId) q.set('to_id', toId);
      return apiFetch<PlanDiff>(`/plan/changes${q.toString() ? `?${q}` : ''}`);
    },
    enabled,
  });
export const verifyVersion = (id: string) => apiFetch<VerifyResult>(`/plan/versions/${id}/verify`);
