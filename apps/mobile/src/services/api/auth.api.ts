import { apiClient } from "./client";
import type { AuthUser } from "../../store/authStore";

interface AuthResponse {
  token: string;
  user: AuthUser;
}

export function loginRequest(email: string, password: string) {
  return apiClient.post<AuthResponse>("/api/auth/login", { email, password }, false);
}

export function registerRequest(email: string, password: string, fullName?: string) {
  return apiClient.post<AuthResponse>("/api/auth/register", { email, password, fullName }, false);
}

export function fetchCurrentUser() {
  return apiClient.get<{ user: AuthUser }>("/api/auth/me");
}
