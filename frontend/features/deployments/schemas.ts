import { z } from "zod";

// ponytail: backend DeploymentStatus has 4 values: pending, deploying,
// active, failed. Mirrored exactly. There is no `cancelled` or `archived`
// status; failed stays in the DB and can be re-activated.
export const deploymentStatusValues = [
  "pending",
  "deploying",
  "active",
  "failed",
] as const;
export type DeploymentStatus = (typeof deploymentStatusValues)[number];

export const DEPLOYMENT_STATUS_LABELS: Record<DeploymentStatus, string> = {
  pending: "Pending",
  deploying: "Deploying",
  active: "Active",
  failed: "Failed",
};

export const DEPLOYMENT_STATUS_VARIANTS: Record<
  DeploymentStatus,
  "secondary" | "info" | "success" | "danger"
> = {
  pending: "secondary",
  deploying: "info",
  active: "success",
  failed: "danger",
};

// ponytail: activation is allowed when the deployment is in a non-active
// pre-load state. The backend rejects re-activation of `active` with 409
// (DEPLOYMENT_ALREADY_ACTIVE). `deploying` is rejected with 409
// (INVALID_DEPLOYMENT_STATUS). Hide the button in both cases.
export function canActivate(status: DeploymentStatus): boolean {
  return status === "pending" || status === "failed";
}

// ponytail: generation only works on active deployments. The backend
// rejects other states with 409 (DEPLOYMENT_NOT_ACTIVE).
export function canGenerate(status: DeploymentStatus): boolean {
  return status === "active";
}

export const MAX_PROMPT_LENGTH = 4096;

export const createDeploymentSchema = z.object({
  model_version_id: z.string().min(1, "Choose a model version."),
  deployment_name: z
    .string()
    .trim()
    .min(1, "Deployment name is required.")
    .max(255, "Deployment name must be 255 characters or fewer."),
  endpoint_name: z
    .string()
    .trim()
    .min(1, "Endpoint name is required.")
    .max(255, "Endpoint name must be 255 characters or fewer."),
});

export type CreateDeploymentInput = z.infer<typeof createDeploymentSchema>;

export type Deployment = {
  id: string;
  owner_id: string;
  model_version_id: string;
  deployment_name: string;
  status: DeploymentStatus;
  endpoint_name: string;
  created_at: string;
  updated_at: string;
};

export type DeploymentList = {
  items: Deployment[];
  total: number;
  limit: number;
  offset: number;
};

export type GenerateResponse_ = {
  response: string;
};
