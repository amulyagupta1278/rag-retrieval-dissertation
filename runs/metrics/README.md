# Metrics directory scope

CSV files in this directory are preserved 100-query expanded automated diagnostic results. They
are not canonical 34-query V2 pilot metrics and do not form five-system Phase 6 comparison.

Canonical five-system pilot registry:

```text
runs/CANONICAL_EVIDENCE.json
```

Canonical balanced metrics:

```text
runs/v2/phase6_seed42_final/metrics/balanced_metrics.json
```

Consolidated byte-identical view:

```text
runs/canonical_v2_pilot/metrics/
```

Root CSV files remain unchanged to prevent mixing automated expanded-benchmark scores with pooled
human-owner pilot judgments.
