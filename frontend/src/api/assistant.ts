/** Hooks for the AI onboarding chat (/assistant/session). */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { components } from './schema';
import { apiFetch } from './http';

type S = components['schemas'];
export type ChatSession = S['SessionRead'];
export type Draft = S['Draft'];
export type ApplyResult = S['ApplyResult'];

const KEY = ['assistant', 'session'];

export const useChatSession = () =>
  useQuery({ queryKey: KEY, queryFn: () => apiFetch<ChatSession>('/assistant/session'), staleTime: Infinity });

export function useSendMessage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (text: string) =>
      apiFetch<ChatSession>('/assistant/session/messages', { method: 'POST', body: JSON.stringify({ text }) }),
    onSuccess: (data) => qc.setQueryData(KEY, data),
  });
}

export function useEditDraft() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (draft: Draft) => apiFetch<ChatSession>('/assistant/session/draft', { method: 'PUT', body: JSON.stringify(draft) }),
    onSuccess: (data) => qc.setQueryData(KEY, data),
  });
}

export function useResetChat() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<ChatSession>('/assistant/session/reset', { method: 'POST' }),
    onSuccess: (data) => qc.setQueryData(KEY, data),
  });
}

export function useApplyChat() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<ApplyResult>('/assistant/session/apply', { method: 'POST' }),
    // Everything the app shows is derived from the saved records: refetch it all.
    onSuccess: () => qc.invalidateQueries(),
  });
}
