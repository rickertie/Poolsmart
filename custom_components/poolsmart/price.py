"""Reading a price forecast out of whatever integration the user happens to use.

There is no standard shape for this. Tibber integrations, Nord Pool, ENTSO-E and
EPEX cards all publish lists of intervals under different attribute names with
different key names inside. Rather than supporting one and failing on the rest,
this parser accepts the shapes that occur in practice and gives up quietly when
it recognises none of them -- at which point the planner simply heats when it
needs to, which is the documented behaviour without price data.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.core import State
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

#: Entity IDs already warned about having no recognisable forecast shape.
#: The shape of a sensor's attributes does not change tick to tick, so once
#: this has been reported there is nothing new to say on the next refresh --
#: without this, a permanently-unrecognised sensor logs the same warning on
#: every coordinator update forever (seen: thousands of times a day).
#: Cleared for an entity as soon as it produces a recognised forecast again,
#: so a real change back to "no forecast" is still reported once.
_warned_no_forecast: set[str] = set()

#: Attribute names that have been seen to hold a list of priced intervals.
#:
#: There is no standard for this. Every tariff integration invents its own shape,
#: so the list grows by observation rather than by specification.
LIST_ATTRIBUTES = (
    "prices_today",
    "prices_tomorrow",
    "today",
    "tomorrow",
    "raw_today",
    "raw_tomorrow",
    "forecast",
    "prices",
    "data",
    # Seen on tibber_prices and similar
    "intervals",
    "today_intervals",
    "tomorrow_intervals",
    "price_data",
    "hourly_prices",
    "all_prices",
    "attributes",
)

#: Keys that have been seen to hold the start of an interval.
START_KEYS = ("start", "starts_at", "start_time", "from", "startsAt", "time")

#: Keys that have been seen to hold the end of an interval.
END_KEYS = ("end", "ends_at", "end_time", "to", "endsAt")

#: Keys that have been seen to hold the all-in price.
PRICE_KEYS = ("total", "price", "value", "total_price", "amount")


def _parse_dt(value) -> datetime | None:
    if isinstance(value, datetime):
        return dt_util.as_local(value)
    if isinstance(value, str):
        parsed = dt_util.parse_datetime(value)
        if parsed is not None:
            return dt_util.as_local(parsed)
    return None


def _first(mapping: dict, keys: tuple[str, ...]):
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _parse_entry(entry, default_length: timedelta) -> tuple | None:
    if not isinstance(entry, dict):
        return None
    start = _parse_dt(_first(entry, START_KEYS))
    if start is None:
        return None
    end = _parse_dt(_first(entry, END_KEYS)) or (start + default_length)
    price = _first(entry, PRICE_KEYS)
    try:
        price = float(price)
    except (TypeError, ValueError):
        return None
    return (start, end, price)


def extract_forecast(state: State | None) -> tuple[tuple[datetime, datetime, float], ...]:
    """Pull a list of priced intervals out of a sensor's attributes."""
    if state is None:
        return ()

    collected: list[tuple] = []
    for name in LIST_ATTRIBUTES:
        raw = state.attributes.get(name)
        if not isinstance(raw, list) or not raw:
            continue
        # Infer the interval length from the first two entries when possible.
        default_length = timedelta(hours=1)
        parsed = [_parse_entry(item, default_length) for item in raw]
        parsed = [p for p in parsed if p is not None]
        if len(parsed) >= 2:
            gap = parsed[1][0] - parsed[0][0]
            if timedelta(minutes=5) <= gap <= timedelta(hours=6):
                parsed = [(s, s + gap, p) for s, _e, p in parsed]
        collected.extend(parsed)

    if not collected:
        # Worth a real warning rather than a debug line: without a forecast the
        # planner cannot choose a cheap moment, and the difference between "no
        # price sensor" and "a price sensor whose shape I do not recognise" is
        # the difference between a setup mistake and a gap in this list. But
        # only once per entity -- the sensor's shape does not change between
        # coordinator refreshes, so repeating it every tick is just noise.
        if state.entity_id not in _warned_no_forecast:
            candidates = [
                name
                for name, value in state.attributes.items()
                if isinstance(value, list) and value
            ]
            _LOGGER.warning(
                "No price forecast recognised on %s. Planning will fall back to "
                "heating on demand. List attributes present: %s",
                state.entity_id,
                candidates or "none",
            )
            _warned_no_forecast.add(state.entity_id)
        return ()

    _warned_no_forecast.discard(state.entity_id)

    # De-duplicate on start time, keep chronological order.
    unique: dict[datetime, tuple] = {}
    for slot in collected:
        unique[slot[0]] = slot
    return tuple(sorted(unique.values(), key=lambda s: s[0]))


def average_price(slots: tuple[tuple[datetime, datetime, float], ...]) -> float | None:
    """Unweighted average price across the forecast.

    Used as the baseline for the savings figure: what the same energy would have
    cost if it had been used at an arbitrary moment instead of a chosen one.
    """
    if not slots:
        return None
    return sum(price for _s, _e, price in slots) / len(slots)
