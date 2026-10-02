/**
 * TypeScript type definitions matching ByteSmiths backend Pydantic schemas.
 */

export interface ProfileResponse {
  id: string;
  monthly_take_home_income_paise: number | null;
  existing_savings_paise: number | null;
  emergency_reserve_paise: number | null;
  monthly_fixed_commitments_paise: number | null;
  monthly_estimated_living_expenses_paise: number | null;
  monthly_estimated_discretionary_paise: number | null;
  unencumbered_savings_paise: number;
  manual_baseline_surplus_paise: number | null;
  is_complete: boolean;
  missing_fields: string[];
  currency: string;
  created_at: string;
  updated_at: string;
}

export interface ProfileUpdateRequest {
  monthly_take_home_income?: string | null;
  monthly_take_home_income_paise?: number | null;
  existing_savings?: string | null;
  existing_savings_paise?: number | null;
  emergency_reserve?: string | null;
  emergency_reserve_paise?: number | null;
  monthly_fixed_commitments?: string | null;
  monthly_fixed_commitments_paise?: number | null;
  monthly_estimated_living_expenses?: string | null;
  monthly_estimated_living_expenses_paise?: number | null;
  monthly_estimated_discretionary?: string | null;
  monthly_estimated_discretionary_paise?: number | null;
  currency?: string | null;
}

export interface GoalResponse {
  id: string;
  user_id: string;
  title: string;
  target_amount_paise: number;
  target_date: string;
  requested_allocated_savings_paise: number;
  permitted_allocated_savings_paise: number | null;
  is_allocation_capped: boolean;
  net_funding_gap_paise: number | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface GoalUpdateRequest {
  title: string;
  target_date: string;
  target_amount?: string;
  target_amount_paise?: number;
  requested_allocated_savings?: string;
  requested_allocated_savings_paise?: number;
}

export interface TimelineBasisResponse {
  current_month: string;
  target_month: string;
  saving_cycles_count: number;
  explanation: string;
}

export type FeasibilityStatus =
  | 'FEASIBLE'
  | 'STRETCH_FEASIBLE'
  | 'INFEASIBLE'
  | 'INSUFFICIENT_DATA';

export interface GoalFeasibilityResponse {
  goal_id: string | null;
  title: string;
  target_amount_paise: number;
  target_date: string;
  months_remaining: number;
  requested_allocated_savings_paise: number;
  permitted_allocated_savings_paise: number | null;
  is_allocation_capped: boolean;
  allocation_capping_note: string | null;
  net_funding_gap_paise: number | null;
  required_monthly_savings_paise: number | null;
  baseline_monthly_surplus_paise: number | null;
  monthly_discretionary_spend_paise: number | null;
  feasibility_status: FeasibilityStatus;
  monthly_shortfall_paise: number | null;
  required_discretionary_cut_paise: number | null;
  months_needed_at_current_surplus: number | null;
  monthly_buffer_paise: number | null;
  missing_baseline_inputs: string[];
  actionable_insight: string;
  timeline_basis: TimelineBasisResponse;
}

export interface ApiError {
  status: number;
  message: string;
  details?: Record<string, unknown> | Array<unknown> | string;
}
