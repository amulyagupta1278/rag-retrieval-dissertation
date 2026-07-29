# Canonical V2 pilot view

This directory consolidates byte-identical views of five frozen retrieval rankings, final Phase 6
metrics/statistics, and benchmark inputs.

```text
runs/canonical_v2_pilot/
├── benchmark/   # R5 questions and final pooled qrels
├── metrics/     # complete Phase 6 metric outputs
├── provenance/  # source and code registries plus frozen manifests
├── retrieval/   # five top-50 ranking files
├── statistics/  # preregistered Phase 6 statistical outputs
└── manifest.json
```

Rebuild deterministically:

```bash
python scripts/build_canonical_v2_view.py --overwrite
```

Files here are convenience copies. Manifest records source path and SHA-256 for every copy.
Historical source files under `runs/v2/` remain authoritative and unchanged.
