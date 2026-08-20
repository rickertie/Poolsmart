> [Home](../index.md) | [Getting Started](../getting_started.md) | [Architecture](../architecture.md) | [Configuration](../configuration.md) | [Troubleshooting](../troubleshooting.md)

---

# Dashboard

This document covers installing and customizing the PoolSmart Lovelace
dashboards. For the main project documentation, see the
[README](../index.md). For the management panel (a separate interface in the
sidebar), see the [README section on the management panel](../index.md#the-management-panel).

---

`dashboard.yaml` is a complete dashboard: three tabs, in Dutch, in a style close
to what most Home Assistant pool dashboards end up looking like.

<p align="center">
  <img src="../images/dashboard-mockup.svg" width="650" alt="PoolSmart three-tab household dashboard alongside the separate maintainer panel at /poolsmart">
</p>
<p align="center"><em>The household dashboard on the left, the maintainer panel on the right — deliberately two different things. See "What Is Deliberately Missing" below.</em></p>

## Installing It

Open the dashboard, click the pencil at the top right, then the three dots, then
**Raw configuration editor**. Select everything that is there and paste the file
over it.

The file starts at `views:`. That matters: a fragment starting at `title:` is a
single view, and pasting one of those into the raw editor is a parse error, not a
mistake on your part.

## Entity Names

Everything assumes the integration is called **Pool**, the default, giving ids
like `sensor.pool_status`. Named it something else? Find and replace `pool_` with
your own.

The part after the prefix is always English and never follows the Home Assistant
language setting. The names shown in the interface are still translated, so you
see "Klaar om" on screen while the id stays `sensor.pool_ready_at`. That split is
deliberate: names are for reading, ids are for referring to, and anything that
gets shared — a dashboard, an automation, a forum post — needs the id to be the
same everywhere.


## Custom Cards

From HACS: `mushroom`, `button-card`, `card-mod`, `apexcharts-card`,
`mini-graph-card`. Remove the cards you do not have; nothing depends on them.

## Two Entities You Must Replace

The temperature graph on the Energie tab points at example source sensors:

```yaml
- entity: sensor.zwembad_controller_temperatuur   # your own water sensor
- entity: sensor.achtertuin_knmi_temperatuur      # your own outdoor sensor
```

PoolSmart does not copy sensors you already have, so point these at your own.
The water temperature is available as an attribute on `sensor.zwembad_status`
for cards, but an attribute cannot be graphed — a graph needs the real sensor.

The Water tab uses `input_number` helpers for pH and chlorine. Water chemistry is
still manual; the integration does not measure or dose anything. Create those
helpers yourself or delete the tab.

## What Is Deliberately Missing

Sensor readings, delta-T, COP, learned values, session history, the planning
timeline and the decision log all live in the **PoolSmart panel** in the sidebar.
Putting them here as well would mean maintaining the same thing in two places,
which is how the previous setup grew to five tabs and became a chore.

This dashboard is for using the pool. The panel is for understanding it.

---

## See Also

- [README](../index.md) — Main project documentation.
- [dashboard.yaml](dashboard.yaml) — Complete three-tab dashboard configuration.
- [docs/sensors.md](../sensors.md) — Sensor mapping & calibration.
- [docs/panel.md](../panel.md) — The management panel (a separate interface).
