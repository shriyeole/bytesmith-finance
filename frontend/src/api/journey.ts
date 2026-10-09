import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { components } from './schema';
import { apiFetch } from './http';

type S = components['schemas'];
export type Journey = S['Journey'];
export type JourneySet = S['JourneySet'];
export type WhatIf = S['WhatIf'];
export type WhatIfComparison = S['WhatIfComparison'];
export type HealthScore = S['HealthScore'];
export type AlertRead = S['AlertRead'];
export type AlertList = S['AlertList'];

export const useJourney = () => useQuery({ queryKey: ['plan', 'journey'], queryFn: () => apiFetch<JourneySet>('/plan/journey') });
export const runWhatIf = (what_if: WhatIf, scenario = 'base') =>
  apiFetch<WhatIfComparison>('/plan/simulate', { method: 'POST', body: JSON.stringify({ scenario, what_if }) });
export const useHealth = () => useQuery({ queryKey: ['plan', 'health'], queryFn: () => apiFetch<HealthScore>('/plan/health') });
export const useAlerts = (includeHidden = false) =>
  useQuery({ queryKey: ['plan', 'alerts', includeHidden], queryFn: () => apiFetch<AlertList>(`/alerts?include_hidden=${includeHidden}`) });
export const useActions = () => useQuery({ queryKey: ['plan', 'actions'], queryFn: () => apiFetch<AlertRead[]>('/plan/actions') });

export function useAlertMutations() {
  const qc = useQueryClient();
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['plan', 'alerts'] });
    qc.invalidateQueries({ queryKey: ['plan', 'actions'] });
  };
  return {
    dismiss: useMutation({ mutationFn: (id: string) => apiFetch<AlertRead>(`/alerts/${id}/dismiss`, { method: 'POST' }), onSuccess: refresh }),
    snooze: useMutation({ mutationFn: ({ id, days }: { id: string; days: number }) => apiFetch<AlertRead>(`/alerts/${id}/snooze`, { method: 'POST', body: JSON.stringify({ days }) }), onSuccess: refresh }),
    done: useMutation({ mutationFn: (id: string) => apiFetch<AlertRead>(`/alerts/${id}/done`, { method: 'POST' }), onSuccess: refresh }),
  };
}
