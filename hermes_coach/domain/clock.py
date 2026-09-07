"""Timestamp handling shared by the persistence services.

Requirement families: `HC-DATA-*`, `HC-PRIVACY`.

The schema stores ISO-8601 UTC text, which sorts correctly as a string only when
every writer uses the same shape. One parser and one formatter live here so a
retention deadline and a confirmation expiry cannot disagree about what a
timestamp means.
"""

from __future__ import annotations

from datetime import datetime, timedelta


TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

_ACCEPTED_FORMATS = ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S")


def parse(value: str) -> datetime:
    """Read a stored timestamp. Naive and `Z`-suffixed forms are both UTC."""
    text = value.replace("Z", "+0000")
    for pattern in _ACCEPTED_FORMATS:
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    raise ValueError(f"unparseable timestamp {value!r}")


def render(moment: datetime) -> str:
    return moment.strftime(TIMESTAMP_FORMAT)


def shift(value: str, delta: timedelta) -> str:
    """Move a stored timestamp by `delta`, keeping the stored shape."""
    return render(parse(value) + delta)
