// apps/web/lib/monitoring.ts
/**
 * Custom frontend monitoring – sends errors to backend for logging in Supabase.
 * No third-party SDK (no Sentry).
 */

export async function reportFrontendError(
  error: Error | string,
  extra: Record<string, any> = {}
) {
  try {
    const message = error instanceof Error ? error.message : error
    const stack = error instanceof Error ? error.stack : undefined

    const payload = {
      message,
      stack,
      url: typeof window !== "undefined" ? window.location.href : "unknown",
      userAgent: typeof navigator !== "undefined" ? navigator.userAgent : "unknown",
      timestamp: new Date().toISOString(),
      ...extra,
    }

    const res = await fetch("/api/monitoring/frontend-error", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      // Include credentials if user is logged in (for user_id association)
      credentials: "include",
    })

    if (!res.ok) {
      console.warn("Failed to report error to backend:", await res.text())
    }
  } catch (reportErr) {
    console.error("Error reporting failed:", reportErr)
  }
}

// ────────────────────────────────────────────────
// Global error handlers (set once on client)
// ────────────────────────────────────────────────
if (typeof window !== "undefined") {
  // Catch unhandled sync errors
  const originalOnError = window.onerror
  window.onerror = (msg, url, line, col, error) => {
    reportFrontendError(error || new Error(String(msg)), {
      source: "window.onerror",
      url,
      line,
      col,
    })
    if (originalOnError) originalOnError(msg, url, line, col, error)
    return false // Allow default console logging
  }

  // Catch unhandled promise rejections
  const originalOnUnhandledRejection = window.onunhandledrejection
  window.onunhandledrejection = (event) => {
    reportFrontendError(event.reason, {
      source: "unhandledrejection",
    })
    if (originalOnUnhandledRejection) originalOnUnhandledRejection(event)
  }
}
