"""Typed return models for fred-mcp tools.

These pydantic models ARE the tool output schemas (the MCP SDK derives
structured-output schemas from them), so every field carries a description.
Lean by design: only the fields an agent acts on.

Copyright pass-through: FRED carries some third-party-copyrighted series whose
``notes`` contain their copyright text. The terms of use forbid stripping such
notices, so ``SeriesInfo.notes`` is returned verbatim and both series models
expose a ``copyrighted`` flag.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SeriesSummary(BaseModel):
    """One search hit — enough to pick a series and call the data tools."""

    series_id: str = Field(description="The FRED series ID (e.g. 'GDPC1', 'UNRATE')")
    title: str = Field(description="Series title")
    units: str = Field(description="Units of the raw data (e.g. 'Percent')")
    frequency: str = Field(description="Native frequency (e.g. 'Monthly', 'Quarterly')")
    seasonal_adjustment: str = Field(description="Seasonal adjustment, short form")
    last_updated: str = Field(description="When the series data was last updated")
    popularity: int | None = Field(
        default=None, description="FRED popularity rank component (higher = more used)"
    )
    copyrighted: bool = Field(
        description="True if this is a third-party-copyrighted series (its notes "
        "carry the owner's terms — check them before non-personal use)"
    )


class SeriesInfo(BaseModel):
    """Full metadata for one series."""

    series_id: str = Field(description="The FRED series ID")
    title: str = Field(description="Series title")
    units: str = Field(description="Units of the raw data")
    frequency: str = Field(description="Native frequency")
    seasonal_adjustment: str = Field(description="Seasonal adjustment")
    observation_start: str = Field(description="First observation date (YYYY-MM-DD)")
    observation_end: str = Field(description="Latest observation date (YYYY-MM-DD)")
    last_updated: str = Field(description="When the series data was last updated")
    popularity: int | None = Field(
        default=None, description="FRED popularity rank component"
    )
    copyrighted: bool = Field(
        description="True if third-party-copyrighted (see notes for the owner's terms)"
    )
    notes: str | None = Field(
        default=None,
        description="The series' FRED notes, verbatim — methodology, caveats, and "
        "any copyright notice (never stripped)",
    )


class Observation(BaseModel):
    """One data point."""

    date: str = Field(description="Observation date (YYYY-MM-DD; period start)")
    value: float | None = Field(
        description="The value, or null where FRED reports a missing value ('.')"
    )


class ObservationsResult(BaseModel):
    """A window of a series' data, optionally transformed."""

    series_id: str = Field(description="The FRED series ID")
    title: str = Field(description="Series title")
    units: str = Field(
        description="Units of the VALUES RETURNED — the native units when "
        "transform='level', otherwise the transform (e.g. '% change from year ago')"
    )
    transform: str = Field(description="The transform applied (level if none)")
    frequency: str = Field(description="Frequency of the values returned")
    observations: list[Observation] = Field(description="The data points, oldest first")
    truncated: bool = Field(
        description="True if more observations exist than were returned — narrow "
        "the date range or raise max_points for more"
    )


class LatestValue(BaseModel):
    """The most recent value of a series, with release context."""

    series_id: str = Field(description="The FRED series ID")
    title: str = Field(description="Series title")
    date: str = Field(description="Date of the latest observation (period start)")
    value: float | None = Field(description="The latest value (null if missing)")
    units: str = Field(description="Units of the value")
    last_updated: str = Field(description="When FRED last updated this series")
    next_release_date: str | None = Field(
        default=None,
        description="The next scheduled release date for this series' release, "
        "if FRED publishes a schedule for it",
    )


class ComparisonSeries(BaseModel):
    """Identity of one series in a comparison."""

    series_id: str = Field(description="The FRED series ID")
    title: str = Field(description="Series title")
    units: str = Field(description="Units of the values returned for this series")
    frequency: str = Field(description="Native frequency of this series")


class ComparisonRow(BaseModel):
    """All series' values on one date."""

    date: str = Field(description="Observation date (YYYY-MM-DD)")
    values: dict[str, float | None] = Field(
        description="series_id -> value on this date (null where a series has no "
        "observation or a missing value)"
    )


class ComparisonResult(BaseModel):
    """Several series aligned on a shared date axis."""

    series: list[ComparisonSeries] = Field(description="The series compared")
    transform: str = Field(description="The transform applied to every series")
    rows: list[ComparisonRow] = Field(description="Aligned values, oldest first")
    truncated: bool = Field(description="True if more rows exist than were returned")


class ReleaseDateEntry(BaseModel):
    """One scheduled or published release date."""

    release_id: int = Field(description="FRED release ID")
    release_name: str = Field(description="Release name (e.g. 'Employment Situation')")
    date: str = Field(description="The release date (YYYY-MM-DD)")


class ReleaseCalendar(BaseModel):
    """Data-release dates within a window."""

    start: str = Field(description="Window start (YYYY-MM-DD)")
    end: str = Field(description="Window end (YYYY-MM-DD)")
    releases: list[ReleaseDateEntry] = Field(
        description="Release dates in the window, soonest first"
    )


class VintageDatesResult(BaseModel):
    """When a series' data was released or revised (its vintages)."""

    series_id: str = Field(description="The FRED series ID")
    total_vintages: int = Field(description="Total number of vintage dates on record")
    first_vintage: str | None = Field(
        default=None,
        description="The earliest vintage date — as-of queries before this date "
        "have no data",
    )
    latest_vintage: str | None = Field(
        default=None, description="The most recent vintage date"
    )
    vintage_dates: list[str] = Field(
        description="Vintage dates, most recent first (capped — see truncated)"
    )
    truncated: bool = Field(
        description="True if total_vintages exceeds the dates listed"
    )


class AsOfResult(BaseModel):
    """A series exactly as it was known on a past date (ALFRED vintage data)."""

    series_id: str = Field(description="The FRED series ID")
    title: str = Field(description="Series title (current title)")
    as_of: str = Field(
        description="The knowledge date — values are as published "
        "on this date, before any later revisions"
    )
    units: str = Field(description="Units of the values")
    observations: list[Observation] = Field(
        description="The data as known on as_of, oldest first"
    )
    truncated: bool = Field(
        description="True if more observations exist than were returned"
    )


class RevisionStep(BaseModel):
    """One value a data point held, and when it held it."""

    value: float | None = Field(description="The value as published")
    published_on: str = Field(
        description="The date this value was published (vintage date)"
    )
    superseded_on: str | None = Field(
        default=None,
        description="The date this value was replaced by a revision (null for "
        "the current value)",
    )
    is_initial: bool = Field(description="True for the first-ever published value")
    is_current: bool = Field(description="True for the value FRED reports today")


class RevisionHistory(BaseModel):
    """The life of one data point across revisions — initial print to today."""

    series_id: str = Field(description="The FRED series ID")
    title: str = Field(description="Series title")
    observation_date: str = Field(
        description="The observation the history is for (period start date)"
    )
    units: str = Field(description="Units of the values")
    initial_value: float | None = Field(
        description="The value as FIRST published (the 'real-time' number)"
    )
    current_value: float | None = Field(
        description="The value as published today, after all revisions"
    )
    total_revision: float | None = Field(
        default=None,
        description="current_value - initial_value (null if either is missing)",
    )
    steps: list[RevisionStep] = Field(
        description="Each distinct value the point has held, oldest first "
        "(consecutive re-publications of an unchanged value are merged)"
    )
