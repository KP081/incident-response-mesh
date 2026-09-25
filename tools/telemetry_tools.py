"""
Real telemetry tools -- logs/metrics live in Postgres (or local sqlite in
dev), not in a static JSON file.

seed_telemetry() acts as a stand-in "ingestion pipeline": right before an
incident is triggered, it writes that scenario's log/metric data into the
real tables with fresh, near-now timestamps -- mimicking data that a real
observability agent would already have written before the alert fired.
query_metrics() and fetch_logs() then do real SQL reads against it, exactly
like a tool talking to Prometheus/Datadog would.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, insert, select

from core.db import get_engine, init_telemetry_tables, service_logs, service_metrics


def _parse_hms(ts: str) -> int:
    h, m, s = map(int, ts.split(":"))
    return h * 3600 + m * 60 + s


def _anchor_log_timestamps(raw_ts: list[str]) -> list[datetime]:
    """Preserves the original spacing between log lines (e.g. 'FATAL 3s
    after the second WARNING') but re-anchors the whole sequence so the
    last line lands at real current time."""
    seconds = [_parse_hms(t) for t in raw_ts]
    span = seconds[-1] - seconds[0]
    now = datetime.now(timezone.utc)
    start = now - timedelta(seconds=span)
    return [start + timedelta(seconds=(s - seconds[0])) for s in seconds]


def _metric_timestamps(count: int, window_minutes: int) -> list[datetime]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=window_minutes)
    if count == 1:
        return [now]
    step = (now - start) / (count - 1)
    return [start + step * i for i in range(count)]


async def seed_telemetry(scenario: dict) -> None:
    """Call this once, right before triggering a scenario."""
    await init_telemetry_tables()
    service = scenario["service"]
    engine = get_engine()

    async with engine.begin() as conn:
        await conn.execute(
            delete(service_logs).where(service_logs.c.service_name == service)
        )
        await conn.execute(
            delete(service_metrics).where(service_metrics.c.service_name == service)
        )

        logs = scenario.get("logs", [])
        if logs:
            timestamps = _anchor_log_timestamps([l["ts"] for l in logs])
            await conn.execute(
                insert(service_logs),
                [
                    {
                        "service_name": service,
                        "ts": ts,
                        "level": l["level"],
                        "msg": l["msg"],
                    }
                    for l, ts in zip(logs, timestamps)
                ],
            )

        metrics = scenario.get("metrics", {})
        window_minutes = metrics.get("window_minutes", 15)
        for metric_name, values in metrics.items():
            if metric_name == "window_minutes":
                continue
            timestamps = _metric_timestamps(len(values), window_minutes)
            await conn.execute(
                insert(service_metrics),
                [
                    {
                        "service_name": service,
                        "metric": metric_name,
                        "ts": ts,
                        "value": v,
                    }
                    for v, ts in zip(values, timestamps)
                ],
            )


async def query_metrics(service_name: str, metric: str, window_minutes: int) -> dict:
    """Query a metric time series for a service over a recent time window.

    Args:
        service_name: The service to query metrics for, e.g. "checkout-service".
        metric: The metric name, e.g. "memory_usage_pct".
        window_minutes: How many minutes of history to return.
    """
    engine = get_engine()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

    async with engine.connect() as conn:
        available = await conn.execute(
            select(service_metrics.c.metric)
            .where(service_metrics.c.service_name == service_name)
            .distinct()
        )
        available_metrics = [row[0] for row in available.fetchall()]

        if metric not in available_metrics:
            if not available_metrics:
                return {
                    "service_name": service_name,
                    "metric": metric,
                    "values": [],
                    "found": False,
                }
            metric = available_metrics[0]

        result = await conn.execute(
            select(service_metrics.c.value)
            .where(
                service_metrics.c.service_name == service_name,
                service_metrics.c.metric == metric,
                service_metrics.c.ts >= cutoff,
            )
            .order_by(service_metrics.c.ts)
        )
        values = [row[0] for row in result.fetchall()]

    return {
        "service_name": service_name,
        "metric": metric,
        "values": values,
        "window_minutes": window_minutes,
        "found": bool(values),
    }


async def fetch_logs(service_name: str, severity: str, limit: int) -> list[dict]:
    """Fetch recent log lines for a service, optionally filtered by severity.

    Args:
        service_name: The service to fetch logs for.
        severity: Minimum severity ("WARNING", "ERROR", "FATAL"), or "ALL".
        limit: Maximum number of log lines to return, most recent first.
    """
    engine = get_engine()

    async with engine.connect() as conn:
        result = await conn.execute(
            select(service_logs.c.ts, service_logs.c.level, service_logs.c.msg)
            .where(service_logs.c.service_name == service_name)
            .order_by(service_logs.c.ts)
        )
        rows = result.fetchall()

    logs = [
        {"ts": r.ts.strftime("%H:%M:%S"), "level": r.level, "msg": r.msg}
        for r in rows
    ]

    if severity != "ALL":
        order = {"INFO": -1, "WARNING": 0, "ERROR": 1, "FATAL": 2}
        min_rank = order.get(severity.upper(), 0)
        logs = [l for l in logs if order.get(l["level"].upper(), -1) >= min_rank]

    return logs[-limit:]