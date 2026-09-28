"""Parse NOAA nClimDiv state-level monthly climate files to tidy parquet.

Source files: data/raw/noaa/climdiv-{tmpcst,pcpnst,pdsist,phdist,pmdist}-v1.0.0-20260707
Format spec + state-code crosswalk: research/r1-noaa-climate.md (verbatim from NOAA state-readme.txt).
Two documented traps handled here:
  1. Missing sentinels differ BY ELEMENT (PDSI-family -99.99, temp -99.90, precip -9.99).
  2. nClimDiv state codes are NOT FIPS (001-050 alphabetical; 101+ are regions) ->
     join downstream on postal code only; regions filtered out here.
Output: data/climate.parquet (state_postal, year, month, tavg_f, precip_in, pdsi, phdi, pmdi) + manifest.
"""
import json
import time
from pathlib import Path

import pandas as pd

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "noaa"
OUT = Path(__file__).resolve().parent.parent / "data" / "climate.parquet"

VERSION = "v1.0.0-20260707"
FILES = {  # element name -> (filename prefix, missing sentinel)
    "tavg_f": ("climdiv-tmpcst", -99.90),
    "precip_in": ("climdiv-pcpnst", -9.99),
    "pdsi": ("climdiv-pdsist", -99.99),
    "phdi": ("climdiv-phdist", -99.99),
    "pmdi": ("climdiv-pmdist", -99.99),
}

# nClimDiv 001-050 numbering (alphabetical lower-48, then HI, AK) -> postal.
# Verbatim order from NOAA state-readme.txt via research/r1-noaa-climate.md §3.
NCLIMDIV_TO_POSTAL = {
    1: "AL", 2: "AZ", 3: "AR", 4: "CA", 5: "CO", 6: "CT", 7: "DE", 8: "FL",
    9: "GA", 10: "ID", 11: "IL", 12: "IN", 13: "IA", 14: "KS", 15: "KY",
    16: "LA", 17: "ME", 18: "MD", 19: "MA", 20: "MI", 21: "MN", 22: "MS",
    23: "MO", 24: "MT", 25: "NE", 26: "NV", 27: "NH", 28: "NJ", 29: "NM",
    30: "NY", 31: "NC", 32: "ND", 33: "OH", 34: "OK", 35: "OR", 36: "PA",
    37: "RI", 38: "SC", 39: "SD", 40: "TN", 41: "TX", 42: "UT", 43: "VT",
    44: "VA", 45: "WA", 46: "WV", 47: "WI", 48: "WY", 49: "HI", 50: "AK",
}


def parse_file(path: Path, sentinel: float) -> pd.DataFrame:
    rows = []
    for line in path.read_text().splitlines():
        if len(line) < 94:
            continue
        state_code = int(line[0:3])
        if state_code > 50:  # regions/basins/national aggregates
            continue
        year = int(line[6:10])
        for m in range(12):
            v = float(line[10 + m * 7 : 17 + m * 7])
            rows.append((NCLIMDIV_TO_POSTAL[state_code], year, m + 1,
                         None if v == sentinel else v))
    return pd.DataFrame(rows, columns=["state_postal", "year", "month", "value"])


def main() -> None:
    t0 = time.time()
    merged = None
    counts = {}
    for element, (prefix, sentinel) in FILES.items():
        path = RAW / f"{prefix}-{VERSION}"
        df = parse_file(path, sentinel).rename(columns={"value": element})
        counts[element] = {"rows": len(df), "non_null": int(df[element].notna().sum())}
        merged = df if merged is None else merged.merge(
            df, on=["state_postal", "year", "month"], how="outer")

    merged = merged.sort_values(["state_postal", "year", "month"]).reset_index(drop=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(OUT, index=False)

    manifest = {
        "source": f"NOAA NCEI nClimDiv state-level monthly, {VERSION} (current through Jun 2026)",
        "source_url": "https://www.ncei.noaa.gov/pub/data/cirs/climdiv/",
        "accessed": "2026-07-12",
        "citation": "Vose et al. (2014), NOAA Monthly U.S. Climate Divisional Database (NClimDiv), doi:10.7289/V5M32STR",
        "script": "pipeline/parse_climate.py",
        "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "rows": int(len(merged)),
        "year_range": [int(merged.year.min()), int(merged.year.max())],
        "states": int(merged.state_postal.nunique()),
        "element_counts": counts,
        "notes": [
            "Sentinels NaN'd per element (temp -99.90, precip -9.99, PDSI-family -99.99).",
            "Region/basin codes (>=101) dropped; 50 states only.",
            "Alaska temp/precip begin 1925 (per NOAA readme); CONUS complete 1895->present.",
        ],
    }
    OUT.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2))

    # Validation against R1's independently decoded sanity values.
    ca2020 = merged.query("state_postal=='CA' and year==2020 and month==12")
    va2020 = merged.query("state_postal=='VA' and year==2020 and month==12")
    print(f"rows={len(merged):,} states={merged.state_postal.nunique()} "
          f"years {merged.year.min()}-{merged.year.max()} in {time.time()-t0:.0f}s")
    print("CA 2020-12 PDSI:", ca2020.pdsi.iloc[0], "(R1 decoded -3.89)")
    print("VA 2020-12 PDSI:", va2020.pdsi.iloc[0], "(R1: positive/wet)")
    assert abs(ca2020.pdsi.iloc[0] - (-3.89)) < 0.005, "CA sanity mismatch"
    assert va2020.pdsi.iloc[0] > 0, "VA sanity mismatch"
    print("SANITY: PASS")


if __name__ == "__main__":
    main()
