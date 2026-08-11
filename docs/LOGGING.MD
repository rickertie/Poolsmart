> [← Back to README](../README.md) | [Getting Started](GETTING_STARTED.MD) | [Architecture](ARCHITECTURE.MD) | [Configuration](CONFIGURATION.MD) | [Troubleshooting](TROUBLESHOOTING.MD)

---

# Logging & Diagnostics

This document covers the three kinds of log entries PoolSmart produces, the
notification system with action buttons, the full ladder trace, and how to
export diagnostics for troubleshooting. For the management panel that displays
diagnostics, see [PANEL.MD](PANEL.MD).

---

## Logbook Entries

Three kinds of entry appear in the standard Home Assistant **Logbook**, alongside
everything else that happened in the house. That context is most of the value: a
pump switching off at 20:00 means one thing alone and another next to "the shed
door opened at 19:58".

### Decisions

What changed, the reason recorded at the moment of deciding, and how long the
previous state lasted. A branch change is logged even when the switches do not
move — the pump staying on for a different reason is still a change of reasoning,
and it used to be invisible.

### Obstacles

What the ladder wanted to do but could not: the price was too high, the mode
excludes it, the heat pump is outside its limits, the night window blocks it.
This is the answer to "why is it not heating", and it is rate limited so a pool
waiting all evening for a cheaper price does not fill the logbook with the same
sentence.

### Faults

Raised and cleared, so the duration is visible rather than inferred from
timestamps.

---

## Notifications You Can Answer

Notifications to a mobile app carry buttons. "Heating postponed" offers *Heat now
anyway* and *Do not heat today*; a flow fault offers *Circulate only* and *Switch
everything off*; the weekly review offers *Apply the suggestion*. Tapping one
acts immediately. Other notify platforms ignore the extra data and receive the
text as normal.

---

## The Full Trace

The panel's Diagnostics tab shows every branch of the ladder for the current
tick, with a verdict for each: chosen, price, outside limits, mode, night, not
applicable, or not reached. The ladder stops at the first match, so branches
below the winner genuinely were not evaluated — saying "not reached" is a fact
about how it works, not an omission.

---

## Sharing a Problem

Settings → Devices & services → PoolSmart → the three dots → **Download
diagnostics**. That file has the trace, the decision log, a plain-sentence
timeline, learned values, faults and every derived figure, with no credentials in
it. It is the fastest way to hand someone the whole picture.

---

## See Also

- [PANEL.MD](PANEL.MD) — The management panel's Diagnostics tab
- [ARCHITECTURE.MD](ARCHITECTURE.MD) — The decision ladder and branch evaluation
- [TROUBLESHOOTING.MD](TROUBLESHOOTING.MD) — What to check when something goes wrong
