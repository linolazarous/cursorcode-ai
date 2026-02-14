"""
app/monitoring/metrics.py
Placeholder for Prometheus metrics.
Add real metrics later if needed.
"""

from prometheus_client import Counter, Histogram, REGISTRY

registry = REGISTRY

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"]
)
