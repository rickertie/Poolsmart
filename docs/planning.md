# Planning

Heating is planned in one of two ways, and the difference is visible in the
interface.

**Maintenance** compensates a day's heat loss. The optimizer picks the
cheapest intervals before the next swimming time and reports a time.

**Seasonal** brings a cold pool up to temperature. That can be ten to
fifteen hours of running, which does not fit in one day of cheap hours, so
the optimizer projects across days and reports a **date**. If the pool loses
heat as fast as the heat pump can add it, it says so instead of producing a
date it cannot meet.

Price forecasts are read from whatever integration you use. Several
attribute shapes are recognised; if none is, planning falls back to heating
on demand.

See [`architecture.md`](architecture.md) for how the heat pump's operating
envelope gates heating sessions in the first place, and
[`learning.md`](learning.md) for how heating rate and COP are learned per
temperature band.
