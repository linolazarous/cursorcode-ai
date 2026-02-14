"""
Monitoring / Prometheus Metrics – CursorCode AI
Centralized Prometheus metrics definitions.
Exported for use in middleware and /metrics endpoint.
Production-ready (2026): consistent labels, detailed error tracking, histograms for latency.
"""

from prometheus_client import Counter, Histogram, REGISTRY

registry = REGISTRY

# ────────────────────────────────────────────────
# HTTP Request Metrics
# ────────────────────────────────────────────────
http_requests_total = Counter(
    name="http_requests_total",
    documentation="Total number of HTTP requests processed",
    labelnames=["method", "path", "status"],
)

http_request_duration_seconds = Histogram(
    name="http_request_duration_seconds",
    documentation="HTTP request duration in seconds",
    labelnames=["method", "path", "status"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float("inf")),
)

http_request_errors_total = Counter(
    name="http_request_errors_total",
    documentation="Total number of HTTP request errors by status code",
    labelnames=["method", "path", "status"],
)

# ────────────────────────────────────────────────
# Database Query Metrics
# ────────────────────────────────────────────────
db_query_duration_seconds = Histogram(
    name="db_query_duration_seconds",
    documentation="Database query duration in seconds",
    labelnames=["query_type", "table"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, float("inf")),
)

db_query_errors_total = Counter(
    name="db_query_errors_total",
    documentation="Total number of database query errors",
    labelnames=["query_type", "table", "error_type"],
)

# ────────────────────────────────────────────────
# Redis Operation Metrics
# ────────────────────────────────────────────────
redis_operation_duration_seconds = Histogram(
    name="redis_operation_duration_seconds",
    documentation="Redis operation duration in seconds",
    labelnames=["operation", "key_type"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, float("inf")),
)

redis_errors_total = Counter(
    name="redis_errors_total",
    documentation="Total number of Redis operation errors",
    labelnames=["operation", "error_type"],
)

# ────────────────────────────────────────────────
# Usage Notes & Integration
# ────────────────────────────────────────────────
"""
In main.py or middleware:

from app.monitoring.metrics import registry

# Expose /metrics endpoint (Prometheus scraping)
@app.get("/metrics")
async def metrics():
    from prometheus_client import generate_latest
    return Response(generate_latest(registry), media_type="text/plain")

# In middleware (example increment):
http_requests_total.labels(
    method=request.method,
    path=request.url.path,
    status=response.status_code
).inc()

http_request_duration_seconds.labels(
    method=request.method,
    path=request.url.path,
    status=response.status_code
).observe(duration_seconds)

# On DB error:
db_query_errors_total.labels(
    query_type="SELECT",
    table="users",
    error_type=type(e).__name__
).inc()
"""
