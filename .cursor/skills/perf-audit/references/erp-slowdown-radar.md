# ERP 8-Dimension Deep Checklist

SSOT: `docs/guides/ERP_SLOWDOWN_RADAR.md`

| dimension | audit question |
|-----------|----------------|
| amplifier | shared partial growth? all-tab impact? |
| render-block | sync/defer scripts on hot pages? |
| interaction-debt | fragment listeners, polling, long tasks? |
| sw-cache | no-cache, networkFirst timeout? |
| query-scale | ilike, .all(), N+1 loops? |
| payload | unbounded list HTML/API? |
| hot-compute | dashboard aggregate cached? |
| io-bound | upload batch blocking? |

Prioritize: user-visible × frequency. high = deploy risk until measured/fixed.
