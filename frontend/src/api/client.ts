/**
 * API client for ByteSmiths Personal Finance Copilot.
 * Connects to FastAPI backend at configurable VITE_API_BASE_URL.
 */

import {
  GoalFeasibilityResponse,
  GoalResponse,
  GoalUpdateRequest,
  ProfileResponse,
  ProfileUpdateRequest,
} from './types';

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string) || 'http://127.0.0.1:8000';

export class ClientError extends Error {
  status: number;
  details?: unknown;

  constructor(status: number, message: string, details?: unknown) {
    super(message);
    this.name = 'ClientError';
    this.status = status;
    this.details = details;
  }
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
    ...options.headers,
  };

  let response: Response;
  try {
    response = await fetch(url, { ...options, headers });
  } catch (err: unknown) {
    const errorMsg =
      err instanceof Error ? err.message : 'Network request failed';
    throw new ClientError(
      0,
      `Cannot connect to backend server at ${API_BASE_URL}. Ensure the FastAPI backend is running. (${errorMsg})`
    );
  }

  if (response.status === 404) {
    // 404 represents normal initial setup state for profile or goal
    throw new ClientError(404, 'Resource not found');
  }

  if (!response.ok) {
    let errorMessage = `Request failed with status ${response.status}`;
    let errorDetails: unknown = undefined;

    try {
      const errorJson = await response.json();
      errorDetails = errorJson;
      if (typeof errorJson.detail === 'string') {
        errorMessage = errorJson.detail;
      } else if (Array.isArray(errorJson.detail)) {
        // Pydantic validation error list
        errorMessage = errorJson.detail
          .map((item: { loc?: string[]; msg?: string }) => {
            const field = item.loc ? item.loc.slice(1).join('.') : '';
            return field ? `${field}: ${item.msg}` : item.msg;
          })
          .filter(Boolean)
          .join('; ');
      }
    } catch {
      // Non-JSON error body
    }

    throw new ClientError(response.status, errorMessage, errorDetails);
  }

  return response.json() as Promise<T>;
}

export const api = {
  /**
   * Retrieve the current financial profile.
   * Returns null if no profile exists yet (HTTP 404).
   */
  async getProfile(): Promise<ProfileResponse | null> {
    try {
      return await request<ProfileResponse>('/profile');
    } catch (err) {
      if (err instanceof ClientError && err.status === 404) {
        return null;
      }
      throw err;
    }
  },

  /**
   * Create or update the financial profile.
   */
  async updateProfile(payload: ProfileUpdateRequest): Promise<ProfileResponse> {
    return request<ProfileResponse>('/profile', {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  },

  /**
   * Retrieve the currently active financial goal.
   * Returns null if no goal exists yet (HTTP 404).
   */
  async getGoal(): Promise<GoalResponse | null> {
    try {
      return await request<GoalResponse>('/goal');
    } catch (err) {
      if (err instanceof ClientError && err.status === 404) {
        return null;
      }
      throw err;
    }
  },

  /**
   * Create or update the active financial goal.
   */
  async updateGoal(payload: GoalUpdateRequest): Promise<GoalResponse> {
    return request<GoalResponse>('/goal', {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  },

  /**
   * Evaluate goal feasibility against the current profile.
   * Returns null if either profile or goal is not found (HTTP 404).
   */
  async getFeasibility(
    currentDate?: string
  ): Promise<GoalFeasibilityResponse | null> {
    try {
      const query = currentDate ? `?current_date=${encodeURIComponent(currentDate)}` : '';
      return await request<GoalFeasibilityResponse>(`/goal/feasibility${query}`);
    } catch (err) {
      if (err instanceof ClientError && err.status === 404) {
        return null;
      }
      throw err;
    }
  },

  /**
   * Health check endpoint to verify backend service readiness.
   */
  async getHealth(): Promise<{ status: string; app: string; version: string }> {
    return request<{ status: string; app: string; version: string }>('/health');
  },
};
