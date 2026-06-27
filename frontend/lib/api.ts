/**
 * Typed API client for the LLM Forge backend.
 *
 * Phase 0 — only the health endpoint is wired.
 * Additional endpoints (datasets, training jobs, evaluations, etc.)
 * will be added in later phases.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export interface ApiSuccess<T> {
  success: true;
  data: T;
  message?: string;
}

export interface ApiError {
  success: false;
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export type ApiResponse<T> = ApiSuccess<T> | ApiError;

export interface HealthData {
  status: string;
  version: string;
  environment: string;
}

export async function getHealth(): Promise<ApiResponse<HealthData>> {
  const res = await fetch(`${API_BASE_URL}/api/v1/health`, {
    cache: "no-store",
  });
  return res.json();
}
