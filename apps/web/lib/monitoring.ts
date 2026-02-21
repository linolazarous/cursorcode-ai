// apps/web/lib/monitoring.ts
/**
 * Frontend Error Monitoring for CursorCode AI
 * Sends client-side errors to backend for logging in Supabase.
 * No third-party services (no Sentry).
 */

export async function reportFrontendError(
  error: Error | string,
  extra: Record<string, any> = {}
) {
  try {
    const message = error instanceof Error ? error.message : error;
    const stack = error instanceof Error ? error.stack : undefined;

    const payload = {
      message,
      stack,
      url: typeof window !== "undefined" ? window.location.href : "server",
      userAgent: typeof navigator !== "undefined" ? navigator.userAgent : "unknown",
      timestamp: new Date().toISOString(),
      ...extra,
    };

    const res = await fetch("/api/monitoring/frontend-error", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      credentials: "include", // Important: allows backend to associate with logged-in user
    });

    if (!res.ok) {
      const errorText = await res.text().catch(() => "Unknown error");
      console.warn("[Monitoring] Failed to report to backend:", errorText);
    } else if (process.env.NODE_ENV === "development") {
      console.log("[Monitoring] Error reported successfully:", message);
    }
  } catch (reportErr) {
    // Fail silently in production to avoid cascading errors
    if (process.env.NODE_ENV === "development") {
      console.error("[Monitoring] Reporting failed:", reportErr);
    }
  }
}

// ────────────────────────────────────────────────
// Global Error Handlers (Client-Side Only)
// Set only once to prevent duplicate listeners
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
    return false; // Let default browser handler also run
  };

  // Catch unhandled promise rejections
  const originalOnUnhandledRejection = window.onunhandledrejection;
  window.onunhandledrejection = (event) => {
    reportFrontendError(event.reason, {
      source: "unhandledrejection",
    });

    if (originalOnUnhandledRejection) originalOnUnhandledRejection(event);
  };
}
