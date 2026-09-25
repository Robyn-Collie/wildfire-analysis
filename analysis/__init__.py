"""Reproducible descriptive analysis of the FPA FOD wildfire record (data/fires.parquet).

Modules:
    common       data loading, region definitions, size-class labels, the claims registry
    descriptive  CLI that computes every descriptive claim and writes outputs/claims.json
    figures      static matplotlib figures written to outputs/figures/

Run from the repo root:
    python -m analysis.descriptive --out outputs/
"""
