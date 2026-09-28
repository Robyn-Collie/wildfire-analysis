"""Extract the FPA-FOD fire records from the capstone's Tableau Hyper file to parquet.

Source: gdb.hyper inside 'Wildfire Analysis Capstone, General Assembly.twbx'
        (FPA-FOD 6th ed. extract; 2,303,566 rows; 1992-2020).
Drops the binary Geometry column (LATITUDE/LONGITUDE carry the location).
Output: data/fires.parquet + a provenance manifest.
"""
import json
import time
import os
from pathlib import Path

import pandas as pd
from tableauhyperapi import Connection, HyperProcess, TableName, Telemetry

# The Tableau extract of FPA FOD this pipeline started from; set WILDFIRE_HYPER to its gdb.hyper path.
HYPER = Path(os.environ.get("WILDFIRE_HYPER", "gdb.hyper"))
OUT = Path(__file__).resolve().parent.parent / "data" / "fires.parquet"
MANIFEST = OUT.with_suffix(".manifest.json")
TABLE = TableName("Extract", "Extract")

t0 = time.time()
OUT.parent.mkdir(parents=True, exist_ok=True)

with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hp:
    with Connection(hp.endpoint, str(HYPER)) as conn:
        td = conn.catalog.get_table_definition(TABLE)
        cols = [c.name.unescaped for c in td.columns if c.name.unescaped != "Geometry"]
        col_sql = ", ".join(f'"{c}"' for c in cols)
        rows = conn.execute_list_query(f"SELECT {col_sql} FROM {TABLE}")

df = pd.DataFrame(rows, columns=cols)
for dc in ("DISCOVERY_DATE", "CONT_DATE"):
    df[dc] = pd.to_datetime(df[dc].astype(str), errors="coerce")
df.to_parquet(OUT, index=False)

manifest = {
    "source": "gdb.hyper (Tableau extract) from 'Wildfire Analysis Capstone, General Assembly.twbx'",
    "upstream": "FPA-FOD 6th edition (Short; USDA RDS-2013-0009.6) -- exact citation in research/r3-provenance-lit.md",
    "script": "pipeline/extract_fires.py",
    "extracted": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "rows": int(len(df)),
    "columns": cols,
    "dropped_columns": ["Geometry (binary TABGEOGRAPHY; LATITUDE/LONGITUDE retained)"],
    "year_range": [int(df["FIRE_YEAR"].min()), int(df["FIRE_YEAR"].max())],
}
MANIFEST.write_text(json.dumps(manifest, indent=2))
print(f"rows={len(df):,}  cols={len(cols)}  -> {OUT}  ({OUT.stat().st_size/1e6:.1f} MB)  in {time.time()-t0:.0f}s")
