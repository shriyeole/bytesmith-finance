/** Typed API + React Query hooks for M1 financial state. Types come from the generated OpenAPI schema. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { components } from './schema';
import { apiFetch, apiFetchOrNull } from './http';

type S = components['schemas'];
export type HouseholdProfile = S['HouseholdProfileRead'];
export type HouseholdProfileUpdate = S['HouseholdProfileUpdate'];
export type Member = S['MemberRead'];
export type Income = S['IncomeRead'];
export type Expense = S['ExpenseRead'];
export type Asset = S['AssetRead'];
export type Liability = S['LiabilityRead'];
export type Policy = S['PolicyRead'];
export type FinancialSummary = S['FinancialSummary'];
export type OnboardingStatus = S['OnboardingStatus'];
export type OnboardingStep = S['OnboardingStep'];
export type Me = S['MeRead'];

export type Collection = 'household/members' | 'incomes' | 'expenses' | 'assets' | 'liabilities' | 'insurance';

export const keys = {
  me: ['me'] as const,
  household: ['household'] as const,
  summary: ['summary'] as const,
  onboarding: ['onboarding'] as const,
  collection: (c: Collection) => ['collection', c] as const,
};

export function useMe() {
  return useQuery({ queryKey: keys.me, queryFn: () => apiFetch<Me>('/me') });
}

export function useHousehold() {
  return useQuery({ queryKey: keys.household, queryFn: () => apiFetchOrNull<HouseholdProfile>('/household') });
}

export function useSaveHousehold() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: HouseholdProfileUpdate) =>
      apiFetch<HouseholdProfile>('/household', { method: 'PUT', body: JSON.stringify(body) }),
    onSuccess: (data) => {
      qc.setQueryData(keys.household, data);
      qc.invalidateQueries({ queryKey: keys.onboarding });
    },
  });
}

export function useSummary() {
  return useQuery({ queryKey: keys.summary, queryFn: () => apiFetch<FinancialSummary>('/financial-state/summary') });
}

export function useOnboarding() {
  return useQuery({ queryKey: keys.onboarding, queryFn: () => apiFetch<OnboardingStatus>('/onboarding') });
}

export function useCompleteStep() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (step: OnboardingStep) =>
      apiFetch<OnboardingStatus>(`/onboarding/steps/${step}/complete`, { method: 'POST' }),
    onSuccess: (data) => qc.setQueryData(keys.onboarding, data),
  });
}

export function useCollection<T>(c: Collection) {
  return useQuery({ queryKey: keys.collection(c), queryFn: () => apiFetch<T[]>(`/${c}`) });
}

/** Create / update / delete for one collection; refreshes the list, summary and onboarding counts. */
export function useCollectionMutations(c: Collection) {
  const qc = useQueryClient();
  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.collection(c) });
    qc.invalidateQueries({ queryKey: keys.summary });
    qc.invalidateQueries({ queryKey: keys.onboarding });
  };
  return {
    create: useMutation({
      mutationFn: (body: Record<string, unknown>) => apiFetch(`/${c}`, { method: 'POST', body: JSON.stringify(body) }),
      onSuccess: refresh,
    }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
        apiFetch(`/${c}/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: string) => apiFetch(`/${c}/${id}`, { method: 'DELETE' }),
      onSuccess: refresh,
    }),
  };
}

export function useDeleteAccount() {
  return useMutation({ mutationFn: () => apiFetch<void>('/me', { method: 'DELETE' }) });
}
