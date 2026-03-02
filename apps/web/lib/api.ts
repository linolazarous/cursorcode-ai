// apps/web/lib/api.ts
import axios, { AxiosInstance, AxiosError } from "axios";
import { signOut } from "./auth";

/**
 * Centralized Axios instance for CursorCode AI
 *
 * Features:
 * - Automatic httpOnly cookie handling (matches your FastAPI backend)
 * - Global 401 → auto sign-out + redirect to signin
 * - Request/response logging in development
 * - Built-in retry for transient errors
 * - Fully compatible with NextAuth v5 + direct FastAPI auth
 */

declare module "axios" {
  export interface InternalAxiosRequestConfig {
    _retry?: boolean;
  }
}

const api: AxiosInstance = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL,
  withCredentials: true,        // ← Critical for your cookie-based auth
  timeout: 15000,
  headers: {
    "Content-Type": "application/json",
  },
});

// ────────────────────────────────────────────────
// Request Interceptor
// ────────────────────────────────────────────────
api.interceptors.request.use(
  (config) => {
    if (process.env.NODE_ENV === "development") {
      console.log(`🚀 [API] ${config.method?.toUpperCase()} ${config.url}`);
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ────────────────────────────────────────────────
// Response Interceptor (401 + retry logic)
// ────────────────────────────────────────────────
api.interceptors.response.use(
  (response) => response,

  async (error: AxiosError) => {
    const originalRequest = error.config as any;

    // 401 → Session expired → sign out
    if (error.response?.status === 401 && !originalRequest?._retry) {
      console.warn("🔑 Session expired. Signing out...");
      originalRequest._retry = true;

      try {
        await signOut({ redirect: true, callbackUrl: "/auth/signin" });
      } catch (e) {
        console.error("Sign-out failed:", e);
      }
      return Promise.reject(error);
    }

    // Optional: simple retry for network flakes (max 1 retry)
    if (
      !originalRequest?._retry &&
      (error.code === "ECONNABORTED" || error.response?.status >= 500)
    ) {
      originalRequest._retry = true;
      return api(originalRequest);
    }

    // Dev error logging
    if (process.env.NODE_ENV === "development") {
      console.error(
        `❌ [API Error] ${error.response?.status} ${originalRequest?.method?.toUpperCase()} ${originalRequest?.url}`,
        error.response?.data || error.message
      );
    }

    return Promise.reject(error);
  }
);

export default api;
