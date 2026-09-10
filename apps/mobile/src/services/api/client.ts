import { API_BASE_URL } from "../../config";
import { useAuthStore } from "../../store/authStore";

export class ApiRequestError extends Error {
  constructor(
    public statusCode: number,
    message: string,
  ) {
    super(message);
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  /** true pour un envoi multipart/form-data (upload photos) — surtout ne pas JSON.stringify. */
  isFormData?: boolean;
  authRequired?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, isFormData = false, authRequired = true } = options;

  const headers: Record<string, string> = {};
  if (!isFormData) {
    headers["Content-Type"] = "application/json";
  }

  const token = useAuthStore.getState().token;
  if (authRequired && token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: isFormData ? (body as FormData) : body ? JSON.stringify(body) : undefined,
  });

  const isJson = response.headers.get("content-type")?.includes("application/json");
  const payload = isJson ? await response.json() : undefined;

  if (!response.ok) {
    const message =
      (payload && typeof payload === "object" && "error" in payload && String(payload.error)) ||
      "Une erreur est survenue. Réessaie dans un instant.";
    throw new ApiRequestError(response.status, message);
  }

  return payload as T;
}

export const apiClient = {
  get: <T>(path: string, authRequired = true) => request<T>(path, { method: "GET", authRequired }),
  post: <T>(path: string, body?: unknown, authRequired = true) =>
    request<T>(path, { method: "POST", body, authRequired }),
  postForm: <T>(path: string, formData: FormData) =>
    request<T>(path, { method: "POST", body: formData, isFormData: true }),
};
