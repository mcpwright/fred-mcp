"""Pure formatting helpers — value parsing, copyright flag, revision steps."""

from fred_mcp.formatting import (
    align_comparison_rows,
    build_revision_steps,
    is_copyrighted,
    to_float,
    total_revision,
)
from fred_mcp.models import Observation


def test_to_float_missing_markers():
    assert to_float(".") is None
    assert to_float("") is None
    assert to_float(None) is None
    assert to_float("-3.8") == -3.8


def test_is_copyrighted():
    assert is_copyrighted({"notes": "Copyright © 2026, Standard & Poor's"}) is True
    assert is_copyrighted({"notes": "Source: BEA."}) is False
    assert is_copyrighted({"notes": None}) is False
    assert is_copyrighted({}) is False


def _rt_row(value: str, start: str, end: str) -> dict:
    return {
        "date": "2008-10-01",
        "value": value,
        "realtime_start": start,
        "realtime_end": end,
    }


def test_build_revision_steps_walk():
    rows = [
        _rt_row("-3.8", "2009-01-30", "2009-02-26"),
        _rt_row("-6.2", "2009-02-27", "2009-03-25"),
        _rt_row("-8.5", "2009-03-26", "9999-12-31"),
    ]
    steps = build_revision_steps(rows)
    assert [s.value for s in steps] == [-3.8, -6.2, -8.5]
    assert steps[0].is_initial and not steps[0].is_current
    assert steps[-1].is_current and steps[-1].superseded_on is None
    assert steps[0].superseded_on == "2009-02-26"
    assert total_revision(steps) == -4.7


def test_build_revision_steps_merges_unchanged_republications():
    rows = [
        _rt_row("-3.8", "2009-01-30", "2009-02-26"),
        _rt_row("-3.8", "2009-02-27", "2009-03-25"),  # re-published, unchanged
        _rt_row("-6.2", "2009-03-26", "9999-12-31"),
    ]
    steps = build_revision_steps(rows)
    assert len(steps) == 2
    assert steps[0].superseded_on == "2009-03-25"  # extended through the merge


def test_build_revision_steps_unsorted_input_is_ordered():
    rows = [
        _rt_row("-6.2", "2009-02-27", "9999-12-31"),
        _rt_row("-3.8", "2009-01-30", "2009-02-26"),
    ]
    steps = build_revision_steps(rows)
    assert [s.value for s in steps] == [-3.8, -6.2]


def test_total_revision_requires_a_current_value():
    steps = build_revision_steps([_rt_row("-3.8", "2009-01-30", "2009-02-26")])
    assert steps[-1].is_current is False
    assert total_revision(steps) is None
    assert total_revision([]) is None


def test_align_comparison_rows_union_with_none_fill():
    rows = align_comparison_rows(
        {
            "A": [Observation(date="2026-01-01", value=1.0)],
            "B": [
                Observation(date="2026-01-01", value=2.0),
                Observation(date="2026-02-01", value=3.0),
            ],
        }
    )
    assert [r.date for r in rows] == ["2026-01-01", "2026-02-01"]
    assert rows[0].values == {"A": 1.0, "B": 2.0}
    assert rows[1].values == {"A": None, "B": 3.0}
