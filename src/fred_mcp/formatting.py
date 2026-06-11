"""Pure helpers shaping raw FRED API payloads into the tool return models.

No I/O here — everything takes parsed JSON and returns models, so it's all
directly unit-testable. Copyright detection: FRED marks third-party-copyrighted
series by carrying the word "Copyright" in their notes (this is the documented
way to find them); we surface that as a boolean and pass the notes through
verbatim (the terms of use forbid stripping proprietary notices).
"""

from __future__ import annotations

from typing import Any

from .fred_client import CURRENT_REALTIME_END
from .models import (
    ComparisonRow,
    Observation,
    RevisionStep,
    SeriesInfo,
    SeriesSummary,
)


def to_float(raw: str | None) -> float | None:
    """FRED encodes a missing value as '.' — map it (and blanks) to None."""
    if raw is None or raw in (".", ""):
        return None
    return float(raw)


def is_copyrighted(series: dict[str, Any]) -> bool:
    """True when the series notes carry a copyright notice."""
    return "copyright" in (series.get("notes") or "").lower()


def to_series_summary(series: dict[str, Any]) -> SeriesSummary:
    return SeriesSummary(
        series_id=series["id"],
        title=series.get("title", ""),
        units=series.get("units", ""),
        frequency=series.get("frequency", ""),
        seasonal_adjustment=series.get("seasonal_adjustment_short", ""),
        last_updated=series.get("last_updated", ""),
        popularity=series.get("popularity"),
        copyrighted=is_copyrighted(series),
    )


def to_series_info(series: dict[str, Any]) -> SeriesInfo:
    return SeriesInfo(
        series_id=series["id"],
        title=series.get("title", ""),
        units=series.get("units", ""),
        frequency=series.get("frequency", ""),
        seasonal_adjustment=series.get("seasonal_adjustment", ""),
        observation_start=series.get("observation_start", ""),
        observation_end=series.get("observation_end", ""),
        last_updated=series.get("last_updated", ""),
        popularity=series.get("popularity"),
        copyrighted=is_copyrighted(series),
        notes=series.get("notes"),
    )


def to_observations(rows: list[dict[str, Any]]) -> list[Observation]:
    """Observation rows -> models, in the order given."""
    return [Observation(date=r["date"], value=to_float(r.get("value"))) for r in rows]


def align_comparison_rows(
    per_series: dict[str, list[Observation]],
) -> list[ComparisonRow]:
    """Merge several series' observations onto one date axis, oldest first.

    A date appears once if ANY series has it; series without an observation on
    that date get None (frequencies should already match — the server enforces
    or harmonizes that before calling this).
    """
    dates: set[str] = set()
    by_series: dict[str, dict[str, float | None]] = {}
    for sid, observations in per_series.items():
        lookup = {o.date: o.value for o in observations}
        by_series[sid] = lookup
        dates.update(lookup)
    return [
        ComparisonRow(
            date=d,
            values={sid: by_series[sid].get(d) for sid in per_series},
        )
        for d in sorted(dates)
    ]


def build_revision_steps(rows: list[dict[str, Any]]) -> list[RevisionStep]:
    """Realtime-period observation rows -> the distinct values a point has held.

    Input rows are FRED ``output_type=1`` observations for ONE observation
    date across the full real-time range: each carries ``realtime_start`` (when
    that value became current), ``realtime_end`` (when it stopped being
    current; 9999-12-31 = still current), and ``value``. Consecutive periods
    with an unchanged value (re-publications without revision) are merged so
    each step is a genuine print or revision.
    """
    ordered = sorted(rows, key=lambda r: r["realtime_start"])
    steps: list[RevisionStep] = []
    for row in ordered:
        value = to_float(row.get("value"))
        end: str | None = row.get("realtime_end")
        if end == CURRENT_REALTIME_END:
            end = None
        if steps and steps[-1].value == value:
            steps[-1].superseded_on = end  # same value re-published — extend
            continue
        steps.append(
            RevisionStep(
                value=value,
                published_on=row["realtime_start"],
                superseded_on=end,
                is_initial=False,
                is_current=False,
            )
        )
    if steps:
        steps[0].is_initial = True
        if steps[-1].superseded_on is None:
            steps[-1].is_current = True
    return steps


def total_revision(steps: list[RevisionStep]) -> float | None:
    """current - initial, when both ends of the history are present."""
    if not steps:
        return None
    initial, current = steps[0].value, steps[-1].value
    if initial is None or current is None or not steps[-1].is_current:
        return None
    return round(current - initial, 10)
