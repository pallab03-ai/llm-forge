import { API_BASE_URL, API_V1_PREFIX } from "@/lib/env";
import { authStorage } from "@/services/auth-storage";
import type { ApiResponse } from "@/types/api";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
  headers?: Record<string, string>;
  skipAuth?: boolean;
};

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const base = `${API_BASE_URL}${API_V1_PREFIX}`;
  const url = new URL(path.startsWith("/") ? path : `/${path}`, `${base}/`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

function authHeader(): Record<string, string> {
  const token = authStorage.getToken();
  return token ? { Authorization: `Bearer ${token.accessToken}` } : {};
}

async function parseResponse<T>(response: Response, sentAuth: boolean): Promise<T> {
  const text = await response.text();
  const payload: ApiResponse<T> = text
    ? (JSON.parse(text) as ApiResponse<T>)
    : { success: true, data: null as T };

  if (!payload.success) {
    if (response.status === 401 && sentAuth) {
      unauthorizedHandler();
    }
    throw new ApiError(payload.error.code, payload.error.message, response.status);
  }
  return payload.data;
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", body, query, headers, skipAuth = false } = options;
  const sentAuth = !skipAuth && authHeader().Authorization !== undefined;

  const response = await fetch(buildUrl(path, query), {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(skipAuth ? {} : authHeader()),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  return parseResponse<T>(response, sentAuth);
}

export const apiClient = {
  get: <T>(path: string, query?: RequestOptions["query"]) =>
    apiRequest<T>(path, { method: "GET", query }),
  post: <T>(path: string, body?: unknown) =>
    apiRequest<T>(path, { method: "POST", body }),
  put: <T>(path: string, body?: unknown) =>
    apiRequest<T>(path, { method: "PUT", body }),
  patch: <T>(path: string, body?: unknown) =>
    apiRequest<T>(path, { method: "PATCH", body }),
  delete: <T>(path: string) => apiRequest<T>(path, { method: "DELETE" }),
};

export type UploadProgressEvent = { loaded: number; total: number };

// ponytail: native `fetch` does not expose upload progress events. XHR is
// the only browser API that does. The function is a thin wrapper that
// mirrors the apiClient envelope contract: throws ApiError on non-success,
// resolves with the unwrapped `data` field on success, and routes a 401
// through the same handler used by apiRequest.
export function uploadFile<T>(
  path: string,
  formData: FormData,
  options: {
    onProgress?: (event: UploadProgressEvent) => void;
    signal?: AbortSignal;
  } = {},
): Promise<T> {
  const { onProgress, signal } = options;
  const url = `${API_BASE_URL}${API_V1_PREFIX}${path.startsWith("/") ? path : `/${path}`}`;
  const token = authStorage.getToken();
  const sentAuth = Boolean(token);

  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress({ loaded: event.loaded, total: event.total });
      }
    });

    xhr.addEventListener("load", () => {
      const text = xhr.responseText;
      let payload: ApiResponse<T>;
      try {
        payload = text
          ? (JSON.parse(text) as ApiResponse<T>)
          : { success: true, data: null as T };
      } catch {
        reject(new ApiError("INVALID_RESPONSE", "Could not parse server response.", xhr.status || 0));
        return;
      }
      if (!payload.success) {
        if (xhr.status === 401 && sentAuth) unauthorizedHandler();
        reject(new ApiError(payload.error.code, payload.error.message, xhr.status || 0));
        return;
      }
      resolve(payload.data);
    });

    xhr.addEventListener("error", () => reject(new TypeError("Network error")));
    xhr.addEventListener("abort", () => reject(new DOMException("Upload aborted", "AbortError")));

    if (signal) {
      if (signal.aborted) {
        xhr.abort();
        return;
      }
      signal.addEventListener("abort", () => xhr.abort());
    }

    xhr.open("POST", url);
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token.accessToken}`);
    // ponytail: the browser sets the multipart boundary. Setting it manually
    // would break the request.
    xhr.send(formData);
  });
}

// ponytail: single module-level 401 hook. AuthProvider registers it on mount.
// Only fires on requests that actually sent the Authorization header, so
// wrong-credential logins surface as normal ApiError instead of redirecting.
let unauthorizedHandler: () => void = () => {};

export function setUnauthorizedHandler(handler: () => void): void {
  unauthorizedHandler = handler;
}
