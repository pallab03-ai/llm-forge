// ponytail: backend exposes 5 monitoring endpoints. Shapes are mirrored
// exactly. There is no chart, no historical series, no time-bucketed API.
// The frontend renders only what the backend returns.

export const healthStateValues = ["healthy", "degraded", "unavailable"] as const;
export type HealthState = (typeof healthStateValues)[number];

export const HEALTH_STATE_LABELS: Record<HealthState, string> = {
  healthy: "Healthy",
  degraded: "Degraded",
  unavailable: "Unavailable",
};

export const HEALTH_STATE_VARIANTS: Record<
  HealthState,
  "success" | "warning" | "danger"
> = {
  healthy: "success",
  degraded: "warning",
  unavailable: "danger",
};

// ponytail: 30 s for the dashboard, 10 s for the per-deployment page.
// TanStack Query pauses polling when the document is hidden by default
// (refetchIntervalInBackground: false), and stops on unmount. No custom
// visibility listener needed.
export const DASHBOARD_POLL_MS = 30_000;
export const DEPLOYMENT_POLL_MS = 10_000;

export const REQUESTS_PAGE_SIZE = 50;
export const ERRORS_PAGE_SIZE = 50;

export type DashboardData = {
  deployment_count: number;
  active_deployments: number;
  failed_deployments: number;
  total_requests: number;
  success_rate: number;
  average_latency_ms: number;
};

export type HealthData = {
  deployment_id: string;
  status: string;
  health: HealthState;
  last_checked: string;
  message: string;
};

export type MetricsData = {
  request_count: number;
  success_count: number;
  failure_count: number;
  average_latency_ms: number;
  min_latency_ms: number;
  max_latency_ms: number;
};

export type RequestStatusValue = "success" | "failure";

export type RequestLogItem = {
  id: string;
  timestamp: string;
  latency_ms: number;
  status: RequestStatusValue;
  prompt_length: number;
  response_length: number | null;
};

export type RequestLogList = {
  items: RequestLogItem[];
  total: number;
  limit: number;
  offset: number;
};

export type ErrorLogItem = {
  timestamp: string;
  error_type: string;
  message: string;
  status_code: number;
};

export type ErrorLogList = {
  items: ErrorLogItem[];
  total: number;
  limit: number;
  offset: number;
};

// ponytail: pure formatters. The backend returns 0.0 for "no data" rather
// than null, so a missing-value distinction only matters for health (which
// may be absent while the row is loading). Number formatters are reused.
const numberFormatter = new Intl.NumberFormat();

export function formatCount(value: number): string {
  return numberFormatter.format(value);
}

export function formatPercentage(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function formatLatencyMs(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(2)} s`;
  return `${Math.round(value)} ms`;
}

export function formatTimestamp(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
