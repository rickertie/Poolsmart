# Self-learning

Learned after each session: heating rate, heat loss, and a COP value per
five degree band of outdoor temperature. Because the heat pump does not
modulate, one value per band is sufficient.

Three rules keep the model honest:

1. Only cleanly closed sessions are used. Interrupted ones, ones with
   faults, and ones too short to measure are recorded and marked, not
   learned from.
2. Every update is capped at a fraction of the current value, so one strange
   session can nudge the model but never replace it.
3. Outliers are rejected on physical grounds — a COP outside the appliance's
   own clamps, water that did not warm up while heating — rather than
   statistically.

Rejected sessions stay in the log with the reason. When the model stops
improving, that is the first place to look.

The learned COP and heating rate feed directly into the planning described
in [`planning.md`](planning.md).
