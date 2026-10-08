/**
 * Legacy single-goal API (profile baseline + one goal + feasibility).
 * Kept working until the M4 goal engine replaces it.
 */

import { apiFetch, apiFetchOrNull } from './http';
import {
  GoalFeasibilityResponse,
  GoalResponse,
  GoalUpdateRequest,
  ProfileResponse,
  ProfileUpdateRequest,
} from './types';

export { ClientError } from './http';

export const api = {
  getProfile: () => apiFetchOrNull<ProfileResponse>('/profile'),
  updateProfile: (payload: ProfileUpdateRequest) =>
    apiFetch<ProfileResponse>('/profile', { method: 'PUT', body: JSON.stringify(payload) }),
  getGoal: () => apiFetchOrNull<GoalResponse>('/goal'),
  updateGoal: (payload: GoalUpdateRequest) =>
    apiFetch<GoalResponse>('/goal', { method: 'PUT', body: JSON.stringify(payload) }),
  getFeasibility: (currentDate?: string) =>
    apiFetchOrNull<GoalFeasibilityResponse>(
      `/goal/feasibility${currentDate ? `?current_date=${encodeURIComponent(currentDate)}` : ''}`
    ),
};
