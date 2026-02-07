// apps/web/lib/monitoring.ts
export async function reportError(error: Error | string, extra: Record<string, any> = {}) {
  try {
    const message = error instanceof Error ? error.message : error;
    const stack = error instanceof Error ? error.stack : undefined;

    await fetch("/api/monitoring/error", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        stack,
        url: window.location.href,
        userAgent: navigator.userAgent,
        ...extra,
      }),
    });
  } catch (e) {
    console.error("Failed to report error:", e);
  }
}

// Global error handlers
if (typeof window !== "undefined") {
  window.onerror = (msg, url, line, col, error) => {
    reportError(error || msg, { source: "window.onerror" });
    return false; // let default handler run too
  };

  window.addEventListener("unhandledrejection", (event) => {
    reportError(event.reason, { source: "unhandledrejection" });
  });
}
