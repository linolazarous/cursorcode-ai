// apps/web/lib/monitoring.ts
/**
 * Frontend Error Monitoring for CursorCode AI
 *
 * Catches all client-side errors and reports them to the backend
 * using the centralized api.ts (with automatic cookie auth).
 */

import api from "./api";

/**
 * Report a frontend error to the backend
 */
export async function reportFrontendError(
  error: Error | string,
  extra: Record<string, any> = {}
) {
  try {
    const message = error instanceof Error ? error.message : error;
    const stack = error instanceof Error ? error.stack : undefined;

    const payload = {
      level: "error",
      message,
      stack,
      url: typeof window !== "undefined" ? window.location.href : "server",
      userAgent: typeof navigator !== "undefined" ? navigator.userAgent : "unknown",
      timestamp: new Date().toISOString(),
      ...extra,
    };

    // Matches your backend router: app.include_router(monitoring.router, prefix="/monitoring")
    await api.post("/monitoring/error", payload);

    if (process.env.NODE_ENV === "development") {
      console.log("[Monitoring] Error reported:", message);
    }
  } catch (reportErr) {
    // Fail silently in production
    if (process.env.NODE_ENV === "development") {
      console.error("[Monitoring] Reporting failed:", reportErr);
    }
  }
}

// ────────────────────────────────────────────────
// Global Error Handlers (runs once per page load)
// ────────────────────────────────────────────────
if (typeof window !== "undefined" && !window.__monitoringInitialized) {
  window.__monitoringInitialized = true;

  // Catch synchronous errors
  const originalOnError = window.onerror;
  window.onerror = (msg, url, line, col, error) => {
    reportFrontendError(error || new Error(String(msg)), {
      source: "window.onerror",
      url,
      line,
      col,
    });
    if (originalOnError) originalOnError(msg, url, line, col, error);
    return false;
  };

  // Catch unhandled promise rejections
  const originalOnUnhandledRejection = window.onunhandledrejection;
  window.onunhandledrejection = (event) => {
    reportFrontendError(event.reason, { source: "unhandledrejection" });
    if (originalOnUnhandledRejection) {
      originalOnUnhandledRejection.call(window, event);
    }
  };
}
