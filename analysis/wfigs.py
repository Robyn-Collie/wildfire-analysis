"""WFIGS incident locations, 2021-2025: a second, separate reporting system layered on top of FPA FOD.

FPA FOD (data/fires.parquet, used by every other module in this package) stops at FIRE_YEAR 2020. WFIGS
(Wildland Fire Interagency Geospatial Services) is the operational system NIFC and its partner agencies use
today to track active incidents. This module pulls WFIGS wildfire ("WF") incident locations discovered
2021-01-01 through 2025-12-31, cleans them, and:

  1. Registers descriptive claims (rows per year, size/cause coverage, fires and acres by year and region,
     the fraction reaching 300 acres, a month x cause "prevention calendar", and a per-state table), each
     compared against FPA FOD 2016-2020 so the site can say plainly whether WFIGS looks like a continuation
     of the FPA FOD series or a different-shaped dataset (it is the latter: WFIGS counts far fewer small,
     non-federal fires -- see wfigs.comparability_verdict).
  2. Forward-tests a reduced-feature version of the large-fire model (analysis/large_fire.py) that predicts
     P(final size >= 300 acres). The full model uses 96 features, most of them from the FPA FOD-Attributes
     join (weather, fuels, terrain, protection status) that does not exist for WFIGS incidents. This module
     therefore trains a small HistGradientBoostingClassifier on only the features both datasets can supply
     (location, day-of-year, cause class, owner class, month) on FPA FOD 2010-2020 CONUS fires, and evaluates
     it -- untouched, no refitting -- on WFIGS 2021-2025 CONUS fires. See wfigs.forward_test_note: this is a
     lower bound on the full model's performance on new data, not a test of the full model itself, because it
     is missing both the weather/fuels/terrain features and is being scored on a different reporting system.

WFIGS is never merged into the FPA FOD series used elsewhere in this package: the two systems count fires
differently (see the comparability section below) and mixing them would silently change the denominator of
every trend the rest of the site computes from data/fires.parquet.

CLI (from the repo root):
    python -m analysis.wfigs --stage {download,analyze,all} --out outputs/

Stages
    download  page through the WFIGS Incident Locations feature service for 2021-2025 wildfires, save the
              raw JSON pages (gzip) and the layer schema under data/external/wfigs/, clean and dedupe to one
              row per fire, and write data/external/wfigs/wfigs_2021_2025.parquet plus a download manifest
              (query, field list, row counts per year, SHA-256, access date).
    analyze   load the parquet, register every wfigs.* claim (descriptive tables, the FPA FOD comparison, the
              comparability verdict, and the forward test), save the reduced model with joblib, and write
              outputs/claims_wfigs.json.
    all       download then analyze.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

from .common import REPO_ROOT, claim, load_fires, region_of, set_source, write_claims
from .large_fire import CAUSE_MAP as FPA_CAUSE_MAP
from .large_fire import NON_CONUS, OWNER_MAP as FPA_OWNER_MAP

log = logging.getLogger('wfigs')

# --------------------------------------------------------------------------- source: WFIGS feature service

# Found from the ArcGIS Online item search (q="WFIGS Incident Locations") and confirmed by reading the layer's
# own JSON (?f=json) on 2026-09-26. The NIFC Open Data page (data-nifc.opendata.arcgis.com) fronts the same
# service. There are three related layers published by NIFC; this module uses the full-history one:
#   - WFIGS_Incident_Locations_YearToDate: current calendar year only (wrong for a 2021-2025 pull).
#   - WFIGS_Incident_Locations_Current: only incidents still open (wrong: most 2021-2024 fires are closed).
#   - WFIGS_Incident_Locations (this one, layer 0 "Incidents"): full history. A count with no filter returned
#     426,988 rows spanning FireDiscoveryDateTime back to 2003, which is only possible on the full-history layer.
SERVICE_URL = ('https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/'
              'WFIGS_Incident_Locations/FeatureServer/0')
LAYER_LABEL = 'WFIGS_Incident_Locations / FeatureServer / 0 ("Incidents", full history, not Year-To-Date)'

# IncidentTypeCategory has three values in this layer: 'WF' (wildfire), 'RX' (prescribed fire) and
# 'CX' (complex, i.e. a parent record grouping several incidents). Only WF is a wildfire discovery.
WHERE_CLAUSE = ("IncidentTypeCategory = 'WF' AND FireDiscoveryDateTime >= TIMESTAMP '2021-01-01 00:00:00' "
               "AND FireDiscoveryDateTime < TIMESTAMP '2026-01-01 00:00:00'")

OUT_FIELDS = [
    'OBJECTID', 'UniqueFireIdentifier', 'IrwinID', 'IncidentName', 'FireDiscoveryDateTime',
    'IncidentSize', 'FinalAcres', 'DiscoveryAcres', 'FireCause', 'FireCauseGeneral',
    'POOState', 'POOLandownerCategory', 'POOLandownerKind', 'POOProtectingAgency',
    'InitialLatitude', 'InitialLongitude', 'IsFSAssisted',
    'ContainmentDateTime', 'ControlDateTime', 'FireOutDateTime',
    'IncidentTypeCategory', 'CreatedOnDateTime_dt', 'ModifiedOnDateTime_dt',
]
PAGE_SIZE = 2000  # the layer's own maxRecordCount (checked via ?f=json); the service caps resultRecordCount here

RAW_DIR = os.path.join(REPO_ROOT, 'data', 'external', 'wfigs')
PAGES_DIR = os.path.join(RAW_DIR, 'raw_pages')
PARQUET_PATH = os.path.join(RAW_DIR, 'wfigs_2021_2025.parquet')
MANIFEST_PATH = os.path.join(RAW_DIR, 'download_manifest.json')
LAYER_META_PATH = os.path.join(RAW_DIR, 'layer_schema.json')

MODEL_OUT_PATH = os.path.join(REPO_ROOT, 'outputs', 'model', 'reduced_g1_hgb.joblib')

# --------------------------------------------------------------------------- HTTP helpers


def _fetch_json(url: str, params: dict[str, Any], timeout: int = 60, retries: int = 5) -> dict[str, Any]:
    qs = urllib.parse.urlencode(params)
    full = f'{url}?{qs}'
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(full, headers={'User-Agent': 'wildfire-analysis-v2/1.0'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
            data = json.loads(body)
            if isinstance(data, dict) and 'error' in data:
                raise RuntimeError(f'WFIGS service error: {data["error"]}')
            return data
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
            last_err = e
            wait = min(2 ** attempt, 20)
            log.warning(f'fetch attempt {attempt}/{retries} failed ({e}); retrying in {wait}s')
            time.sleep(wait)
    raise RuntimeError(f'WFIGS fetch failed after {retries} attempts for {url}: {last_err}')


# --------------------------------------------------------------------------- stage: download


def stage_download(out: str) -> dict[str, Any]:
    os.makedirs(PAGES_DIR, exist_ok=True)
    access_date = pd.Timestamp.now(tz='UTC').date().isoformat()

    log.info(f'reading layer schema from {SERVICE_URL}?f=json')
    layer = _fetch_json(SERVICE_URL, {'f': 'json'})
    field_names = [f['name'] for f in layer.get('fields', [])]
    max_record_count = layer.get('maxRecordCount')
    with open(LAYER_META_PATH, 'w') as f:
        json.dump(layer, f, indent=1)
    missing = [c for c in OUT_FIELDS if c not in field_names and c != 'OBJECTID']
    if missing:
        raise RuntimeError(f'requested fields not present on the layer: {missing}')
    log.info(f'layer "{layer.get("name")}": {len(field_names)} fields, maxRecordCount={max_record_count}')

    total = _fetch_json(SERVICE_URL + '/query', {
        'where': WHERE_CLAUSE, 'returnCountOnly': 'true', 'f': 'json'})['count']
    log.info(f'query matches {total:,} rows: {WHERE_CLAUSE}')

    rows: list[dict[str, Any]] = []
    offset = 0
    page_no = 0
    while True:
        params = {
            'where': WHERE_CLAUSE,
            'outFields': ','.join(OUT_FIELDS),
            'returnGeometry': 'true',
            'outSR': 4326,
            'orderByFields': 'OBJECTID',
            'resultOffset': offset,
            'resultRecordCount': PAGE_SIZE,
            'f': 'json',
        }
        page = _fetch_json(SERVICE_URL + '/query', params)
        feats = page.get('features', [])
        page_path = os.path.join(PAGES_DIR, f'page_{offset:06d}.json.gz')
        with gzip.open(page_path, 'wt') as f:
            json.dump(page, f)
        rows.extend(feats)
        page_no += 1
        log.info(f'page {page_no}: offset {offset:,}, {len(feats)} rows, {len(rows):,} total so far')
        if len(feats) < PAGE_SIZE and not page.get('exceededTransferLimit'):
            break
        offset += PAGE_SIZE
        if offset > total + PAGE_SIZE:  # safety valve against an infinite loop if paging misbehaves
            raise RuntimeError(f'paging exceeded the expected row count ({total:,}) without terminating')

    if len(rows) != total:
        log.warning(f'fetched {len(rows):,} rows but the count query reported {total:,}; the service may have '
                    'been updated between the two calls (WFIGS is live operational data)')

    raw = _rows_to_frame(rows)
    clean, clean_info = _clean(raw)
    clean.to_parquet(PARQUET_PATH, index=False)
    sha256 = hashlib.sha256(open(PARQUET_PATH, 'rb').read()).hexdigest()

    rows_per_year_raw = raw.assign(year=pd.to_datetime(raw.FireDiscoveryDateTime, unit='ms', utc=True).dt.year
                                    ).groupby('year').size().to_dict()

    manifest = {
        'service_url': SERVICE_URL,
        'layer_label': LAYER_LABEL,
        'layer_name': layer.get('name'),
        'max_record_count': max_record_count,
        'field_count_on_layer': len(field_names),
        'fields_requested': OUT_FIELDS,
        'where_clause': WHERE_CLAUSE,
        'out_sr': 4326,
        'page_size': PAGE_SIZE,
        'n_pages': page_no,
        'access_date_utc': access_date,
        'rows_fetched_raw': len(rows),
        'rows_reported_by_count_query': total,
        'rows_per_year_raw': {int(k): int(v) for k, v in sorted(rows_per_year_raw.items())},
        'rows_after_cleaning': int(len(clean)),
        'cleaning': clean_info,
        'parquet_path': PARQUET_PATH,
        'parquet_sha256': sha256,
        'raw_pages_dir': PAGES_DIR,
    }
    with open(MANIFEST_PATH, 'w') as f:
        json.dump(manifest, f, indent=1)
    log.info(f'wrote {PARQUET_PATH} ({len(clean):,} rows after cleaning), sha256={sha256[:16]}...')
    return manifest


def _rows_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    recs = []
    for r in rows:
        attrs = dict(r.get('attributes', {}))
        geom = r.get('geometry') or {}
        attrs['geom_x'] = geom.get('x')
        attrs['geom_y'] = geom.get('y')
        recs.append(attrs)
    return pd.DataFrame.from_records(recs)


# --------------------------------------------------------------------------- cleaning

CAUSE_CLASS_MAP = {
    'Human': 'Human',
    'Natural': 'Natural',
    'Undetermined': 'Missing',
    'Unknown': 'Missing',
}
CAUSE_CLASS_DEFINITION = ("WFIGS FireCause mapped to Human / Natural / Missing: FireCause='Human' -> Human, "
                          "'Natural' -> Natural, 'Undetermined', 'Unknown' or null -> Missing. This mirrors the "
                          "FPA FOD-side mapping in analysis.large_fire (NWCG_CAUSE_CLASSIFICATION -> Human / "
                          "Natural / Missing) so the two datasets share one cause-class scheme.")

# POOLandownerCategory (fine-grained) mapped to the same six owner classes analysis.large_fire.OWNER_MAP uses for
# FPA FOD's OWNER_DESCR, so the forward-test features line up across datasets. ANCSA (Alaska Native Claims
# Settlement Act corporation land) has no FPA FOD equivalent; it is grouped with Tribal as the closest available
# category (Alaska is excluded from the CONUS forward test in any case, so this only affects descriptive tables).
WFIGS_OWNER_MAP = {
    'USFS': 'Federal', 'BLM': 'Federal', 'NPS': 'Federal', 'USFWS': 'Federal', 'BOR': 'Federal', 'BIA': 'Federal',
    'DOD': 'Federal', 'DOE': 'Federal', 'OthFed': 'Federal',
    'State': 'State',
    'Private': 'Private',
    'Tribal': 'Tribal', 'ANCSA': 'Tribal',
    'City': 'Other', 'County': 'Other', 'OthLoc': 'Other', 'Foreign': 'Other',
}
WFIGS_OWNER_DEFINITION = ("WFIGS POOLandownerCategory mapped: Federal = USFS BLM NPS USFWS BOR BIA DOD DOE OthFed; "
                          "State = State; Private = Private; Tribal = Tribal, ANCSA (Alaska Native corporation "
                          "land, no FPA FOD equivalent); Other = City County OthLoc Foreign; Missing = null. "
                          "Matches analysis.large_fire.OWNER_MAP's FPA FOD-side mapping class for class.")


def _epoch_ms_to_datetime(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, unit='ms', utc=True, errors='coerce')


def _clean(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """One row per fire, typed columns, documented drops. Returns (clean_df, info)."""
    df = raw.copy()
    n_raw = len(df)

    n_dupe_rows = 0
    if 'UniqueFireIdentifier' in df.columns:
        before = len(df)
        df = df.sort_values('OBJECTID').drop_duplicates('UniqueFireIdentifier', keep='last')
        n_dupe_rows = before - len(df)

    df['discovery_dt'] = _epoch_ms_to_datetime(df['FireDiscoveryDateTime'])
    df['containment_dt'] = _epoch_ms_to_datetime(df.get('ContainmentDateTime'))
    df['control_dt'] = _epoch_ms_to_datetime(df.get('ControlDateTime'))
    df['fire_out_dt'] = _epoch_ms_to_datetime(df.get('FireOutDateTime'))

    lat = pd.to_numeric(df['InitialLatitude'], errors='coerce')
    lon = pd.to_numeric(df['InitialLongitude'], errors='coerce')
    gx = pd.to_numeric(df.get('geom_x'), errors='coerce')
    gy = pd.to_numeric(df.get('geom_y'), errors='coerce')
    df['latitude'] = lat.where(lat.notna(), gy)
    df['longitude'] = lon.where(lon.notna(), gx)
    n_location_from_geometry = int(((lat.isna() | lon.isna()) & df['latitude'].notna() & df['longitude'].notna()).sum())

    # Size field precedence, documented: IncidentSize (the incident's most recently reported / final acreage as
    # tracked through IRWIN, the closest analog to FPA FOD's FIRE_SIZE) first; FinalAcres (the number on an
    # approved final fire report) second, since it is far sparser (about 16% of rows) but authoritative when
    # present; DiscoveryAcres (the size at first report, so it understates any fire that grew) last, only to
    # recover rows the other two fields miss.
    inc = pd.to_numeric(df['IncidentSize'], errors='coerce')
    fin = pd.to_numeric(df['FinalAcres'], errors='coerce')
    disc = pd.to_numeric(df['DiscoveryAcres'], errors='coerce')
    size = inc.where(inc.notna(), fin)
    size = size.where(size.notna(), disc)
    df['size_acres'] = size
    df['size_source'] = np.select([inc.notna(), fin.notna(), disc.notna()],
                                  ['IncidentSize', 'FinalAcres', 'DiscoveryAcres'], default='none')

    df['state'] = df['POOState'].astype(str).str.replace('US-', '', regex=False)
    df.loc[df['POOState'].isna(), 'state'] = None
    df['cause_class'] = df['FireCause'].astype(str).map(CAUSE_CLASS_MAP).fillna('Missing')
    df.loc[df['FireCause'].isna(), 'cause_class'] = 'Missing'
    df['owner_class'] = df['POOLandownerCategory'].astype(str).map(WFIGS_OWNER_MAP)
    df.loc[df['POOLandownerCategory'].isna(), 'owner_class'] = 'Missing'
    df['owner_class'] = df['owner_class'].fillna('Missing')

    df['year'] = df['discovery_dt'].dt.year
    df['month'] = df['discovery_dt'].dt.month
    sin, cos = _doy_sin_cos(df['discovery_dt'])
    df['sin_doy'], df['cos_doy'] = sin, cos
    df['region'] = region_of(pd.Series(df['state'].fillna('').to_numpy()))
    df['cell'] = (np.floor(df['latitude']).astype('Int64').astype(str) + '_'
                  + np.floor(df['longitude']).astype('Int64').astype(str))
    df.loc[df['latitude'].isna() | df['longitude'].isna(), 'cell'] = None

    no_location = int((df['latitude'].isna() | df['longitude'].isna()).sum())
    no_discovery_date = int(df['discovery_dt'].isna().sum())
    drop_mask = df['latitude'].isna() | df['longitude'].isna() | df['discovery_dt'].isna()
    clean = df.loc[~drop_mask].reset_index(drop=True)

    keep_cols = ['UniqueFireIdentifier', 'IrwinID', 'IncidentName', 'discovery_dt', 'year', 'month',
                 'sin_doy', 'cos_doy', 'latitude', 'longitude', 'cell', 'state', 'region',
                 'size_acres', 'size_source', 'FireCause', 'FireCauseGeneral', 'cause_class',
                 'POOLandownerCategory', 'POOLandownerKind', 'owner_class', 'POOProtectingAgency',
                 'IsFSAssisted', 'containment_dt', 'control_dt', 'fire_out_dt']
    clean = clean[keep_cols].rename(columns={'FireCause': 'fire_cause_raw', 'FireCauseGeneral': 'fire_cause_general',
                                              'POOLandownerCategory': 'poo_landowner_category',
                                              'POOLandownerKind': 'poo_landowner_kind',
                                              'POOProtectingAgency': 'poo_protecting_agency'})

    info = {
        'n_raw_rows_fetched': int(n_raw),
        'n_duplicate_rows_dropped_on_unique_fire_identifier': int(n_dupe_rows),
        'n_rows_with_location_recovered_from_geometry_xy': n_location_from_geometry,
        'n_dropped_no_location': no_location,
        'n_dropped_no_discovery_date': no_discovery_date,
        'n_dropped_total': int(drop_mask.sum()),
        'n_after_cleaning': int(len(clean)),
        'size_field_precedence': 'IncidentSize, then FinalAcres, then DiscoveryAcres (see code comment)',
        'size_source_counts': {k: int(v) for k, v in clean['size_source'].value_counts().to_dict().items()},
        'cause_class_definition': CAUSE_CLASS_DEFINITION,
        'owner_class_definition': WFIGS_OWNER_DEFINITION,
        'dedup_key': 'UniqueFireIdentifier (kept the row with the largest OBJECTID, i.e. the most recently synced)',
    }
    return clean, info


def _doy_sin_cos(dt: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Leap-aware angle, identical construction to analysis.large_fire._doy_angle."""
    doy = dt.dt.dayofyear.to_numpy(dtype=float) - 1
    diy = np.where(dt.dt.is_leap_year.to_numpy(), 366, 365)
    valid = dt.notna().to_numpy()
    ang = np.where(valid, 2 * np.pi * doy / np.where(diy == 0, 365, diy), np.nan)
    return np.sin(ang), np.cos(ang)


# --------------------------------------------------------------------------- climatology (copied)

def climatology(train: pd.DataFrame, test: pd.DataFrame, target: str, k: float = 20.0) -> np.ndarray:
    """P(target) by 1-degree cell x month from training rows, smoothed with k pseudo-counts toward the
    cell rate, which is itself smoothed toward the global rate; backs off cell x month -> cell -> global.

    Copied verbatim from analysis.large_fire.climatology on 2026-09-26 so this module has no runtime
    dependency on large_fire's heavier build_sample() pipeline. train/test need CELL and MONTH columns."""
    prior = float(train[target].mean())
    c = train.groupby('CELL', observed=True)[target].agg(['sum', 'count'])
    c['p'] = (c['sum'] + k * prior) / (c['count'] + k)
    g = train.groupby(['CELL', 'MONTH'], observed=True)[target].agg(['sum', 'count']).reset_index()
    g['cell_p'] = g.CELL.map(c['p'])
    g['p'] = (g['sum'] + k * g['cell_p']) / (g['count'] + k)
    g = g.set_index(['CELL', 'MONTH'])['p']
    cp = pd.Series(c['p'].reindex(test.CELL).to_numpy(), index=test.index).fillna(prior)
    key = pd.MultiIndex.from_arrays([test.CELL, test.MONTH])
    p = pd.Series(g.reindex(key).to_numpy(), index=test.index).fillna(cp)
    return p.to_numpy(dtype=float)


# --------------------------------------------------------------------------- descriptive claims

MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
LARGE_ACRES = 300.0


def _by_year_region_table(df: pd.DataFrame, size_col: str) -> dict[str, Any]:
    by_year = df.groupby('year').agg(fires=('year', 'size'), acres=(size_col, 'sum'),
                                      fires_ge300=(size_col, lambda s: int((s >= LARGE_ACRES).sum())))
    by_year['share_ge300'] = by_year['fires_ge300'] / by_year['fires']
    by_region = df.groupby('region').agg(fires=('region', 'size'), acres=(size_col, 'sum'),
                                          fires_ge300=(size_col, lambda s: int((s >= LARGE_ACRES).sum())))
    by_region['share_ge300'] = by_region['fires_ge300'] / by_region['fires']
    return {'by_year': by_year.reset_index().to_dict('records'),
           'by_region': by_region.reset_index().to_dict('records')}


def register_descriptive_claims(clean: pd.DataFrame, manifest: dict[str, Any]) -> None:
    n = len(clean)
    claim('wfigs.source_service', {'url': SERVICE_URL, 'layer': LAYER_LABEL,
                                   'max_record_count': manifest['max_record_count'],
                                   'field_count_on_layer': manifest['field_count_on_layer']},
         'The ArcGIS Online feature service and layer queried for WFIGS incident locations.', n=None)
    claim('wfigs.query', {'where': WHERE_CLAUSE, 'out_fields': OUT_FIELDS, 'out_sr': 4326,
                          'page_size': PAGE_SIZE, 'n_pages': manifest['n_pages']},
         'The exact query used to page through the layer.', n=None)
    claim('wfigs.access_date', manifest['access_date_utc'], 'UTC date the service was queried.', n=None)
    claim('wfigs.parquet_sha256', manifest['parquet_sha256'],
         'SHA-256 of data/external/wfigs/wfigs_2021_2025.parquet as written.', n=None)
    claim('wfigs.rows_fetched_raw', manifest['rows_fetched_raw'],
         'Raw rows returned by the query before dedup/cleaning (IncidentTypeCategory=WF, discovery '
         '2021-01-01 to 2025-12-31).', n=manifest['rows_fetched_raw'])
    claim('wfigs.cleaning', manifest['cleaning'],
         'Row counts dropped at each cleaning step: duplicate UniqueFireIdentifier, no location, no '
         'discovery date. See analysis/wfigs.py:_clean.', n=manifest['rows_fetched_raw'])
    claim('wfigs.rows_per_year', clean.groupby('year').size().to_dict(),
         'Cleaned WFIGS wildfire rows (IncidentTypeCategory=WF) by discovery year, 2021-2025.', n=n)
    claim('wfigs.rows_with_size', {'n': int(clean['size_acres'].notna().sum()),
                                   'share': float(clean['size_acres'].notna().mean())},
         'Rows with a non-null size_acres (IncidentSize, else FinalAcres, else DiscoveryAcres).', n=n)
    claim('wfigs.share_missing_cause', float((clean['cause_class'] == 'Missing').mean()),
         'Share of cleaned rows with cause_class = Missing (FireCause null, Undetermined or Unknown).', n=n)
    claim('wfigs.share_by_cause_class', (clean['cause_class'].value_counts(normalize=True)).to_dict(),
         'Share of cleaned rows by cause_class (Human / Natural / Missing).', n=n)

    sized = clean[clean['size_acres'].notna()].copy()
    tables = _by_year_region_table(sized, 'size_acres')
    claim('wfigs.fires_acres_by_year', tables['by_year'],
         'Fires, summed size_acres, fires >= 300 acres and their share, by discovery year, for the rows with '
         'a size.', n=len(sized))
    claim('wfigs.fires_acres_by_region', tables['by_region'],
         'Same measures as wfigs.fires_acres_by_year, by region (analysis.common.region_of on the POOState '
         'state code).', n=len(sized))

    cal = (clean.groupby(['month', 'cause_class']).size().unstack(fill_value=0))
    cal.index = [MONTH_ABBR[m - 1] for m in cal.index]
    claim('wfigs.month_x_cause_calendar', cal.to_dict('index'),
         'Fire counts by discovery month x cause_class, 2021-2025: the WFIGS analog of a fire-prevention '
         'calendar.', n=n)

    st = clean.copy()
    st['known_cause'] = st['cause_class'].isin(['Human', 'Natural'])
    per_state = st.groupby('state').apply(lambda g: pd.Series({
        'fires': len(g), 'acres': float(g['size_acres'].sum(skipna=True)),
        'fires_ge300': int((g['size_acres'] >= LARGE_ACRES).sum()),
        'human_share_of_known_cause': (float((g['cause_class'] == 'Human').sum() / g['known_cause'].sum())
                                       if g['known_cause'].sum() > 0 else None),
    }), include_groups=False).reset_index()
    claim('wfigs.per_state_2021_2025', per_state.to_dict('records'),
         'Per-state fires, acres, fires >= 300 acres and human share of known cause (Human / (Human + '
         'Natural)), WFIGS 2021-2025, state = POOState.', n=n)


def register_fpa_comparison(clean: pd.DataFrame) -> None:
    fpa = load_fires(['FIRE_YEAR', 'STATE', 'FIRE_SIZE', 'NWCG_CAUSE_CLASSIFICATION', 'DISCOVERY_DATE'])
    fpa = fpa[(fpa.FIRE_YEAR >= 2016) & (fpa.FIRE_YEAR <= 2020)].copy()
    fpa['region'] = region_of(fpa.STATE)
    fpa['cause_class'] = fpa.NWCG_CAUSE_CLASSIFICATION.astype(str).map(FPA_CAUSE_MAP).fillna('Missing')
    n_fpa = len(fpa)

    fpa_rows_per_year = fpa.groupby('FIRE_YEAR').size().to_dict()
    fpa_share_missing_cause = float((fpa['cause_class'] == 'Missing').mean())
    fpa_tables = _by_year_region_table(fpa.rename(columns={'FIRE_YEAR': 'year'}), 'FIRE_SIZE')

    wfigs_mean_per_year = float(pd.Series(list(dict(zip(*np.unique(clean['year'], return_counts=True))).values())).mean())
    fpa_mean_per_year = float(pd.Series(list(fpa_rows_per_year.values())).mean())

    comparison = {
        'fpa_fod_2016_2020': {
            'n': n_fpa, 'rows_per_year': {int(k): int(v) for k, v in fpa_rows_per_year.items()},
            'mean_rows_per_year': fpa_mean_per_year,
            'share_missing_cause': fpa_share_missing_cause,
            'share_by_cause_class': fpa['cause_class'].value_counts(normalize=True).to_dict(),
            'by_year': fpa_tables['by_year'], 'by_region': fpa_tables['by_region'],
        },
        'wfigs_2021_2025': {
            'n': len(clean), 'mean_rows_per_year': wfigs_mean_per_year,
        },
        'ratio_wfigs_to_fpa_mean_rows_per_year': wfigs_mean_per_year / fpa_mean_per_year,
    }
    claim('wfigs.comparison_fpa_fod_2016_2020', comparison,
         'The same measures (rows per year, missing-cause share, cause-class share, fires/acres by year and '
         'region) computed on FPA FOD 2016-2020 (all states), for comparison against WFIGS 2021-2025. Two '
         'different reporting systems: WFIGS is not a continuation of the FPA FOD series, and no number here '
         'is merged into data/fires.parquet or the rest of this package.', n=n_fpa)

    wf_sized_ge300_share = float((clean.loc[clean.size_acres.notna(), 'size_acres'] >= LARGE_ACRES).mean())
    fpa_ge300_share = float((fpa.FIRE_SIZE >= LARGE_ACRES).mean())
    ratio_pct = comparison['ratio_wfigs_to_fpa_mean_rows_per_year'] * 100
    verdict = (
        f"WFIGS 2021-2025 averages {wfigs_mean_per_year:,.0f} wildfire (WF) records a year against FPA FOD "
        f"2016-2020's {fpa_mean_per_year:,.0f} a year, about {ratio_pct:.0f}% as many. This is not a data-quality "
        "problem in WFIGS; it is a scope difference. FPA FOD compiles reports from federal, state, and many "
        "local and volunteer fire departments, so it captures a large number of very small (Class A and B) fires "
        "that local agencies log but that never enter the interagency IRWIN system WFIGS is built on. WFIGS is "
        "close to complete for fires that get a federal or state incident record, and its fires-reaching-300-acres "
        f"rate ({wf_sized_ge300_share:.1%} of sized rows) is higher than FPA FOD 2016-2020's ({fpa_ge300_share:.1%}), "
        "consistent with WFIGS undercounting small fires relative to FPA FOD rather than missing large ones. The "
        f"missing-cause share also differs ({float((clean['cause_class']=='Missing').mean()):.1%} in WFIGS vs "
        f"{fpa_share_missing_cause:.1%} in FPA FOD 2016-2020), which the site should not read as WFIGS reporting "
        "cause worse; it reflects a different mix of reporting agencies and a different lag before a cause is "
        "finalized on an incident that may still be open at query time. Conclusion for the site: WFIGS 2021-2025 "
        "can be shown as its own recent-years panel (fires, acres, cause mix, regional pattern, the 300-acre "
        "share) but should never be spliced onto the FPA FOD 1992-2020 series as if it were the next five years "
        "of the same count; the denominators are not comparable."
    )
    claim('wfigs.comparability_verdict', verdict,
         'Plain-language verdict on whether WFIGS 2021-2025 is comparable to FPA FOD as a continuing series.',
         n=None)


# --------------------------------------------------------------------------- forward test

REDUCED_FEATURES = ['LATITUDE', 'LONGITUDE', 'SIN_DOY', 'COS_DOY', 'CAUSE_CLASS', 'OWNER_CLASS', 'MONTH']
REDUCED_CATEGORICAL = ['CAUSE_CLASS', 'OWNER_CLASS']
CAUSE_CATEGORIES = ['Human', 'Natural', 'Missing']
OWNER_CATEGORIES = ['Federal', 'State', 'Private', 'Tribal', 'Other', 'Missing']
HGB_PARAMS = dict(learning_rate=0.05, max_leaf_nodes=63, min_samples_leaf=50, l2_regularization=1.0,
                  max_iter=500, early_stopping=True, random_state=42)


def _build_fpa_features() -> pd.DataFrame:
    cols = ['FIRE_YEAR', 'DISCOVERY_DATE', 'LATITUDE', 'LONGITUDE', 'STATE', 'FIRE_SIZE',
           'NWCG_CAUSE_CLASSIFICATION', 'OWNER_DESCR']
    fpa = load_fires(cols)
    fpa = fpa[(fpa.FIRE_YEAR >= 2010) & (fpa.FIRE_YEAR <= 2020)]
    fpa = fpa[~fpa.STATE.astype(str).isin(NON_CONUS)].copy()
    sin, cos = _doy_sin_cos(fpa['DISCOVERY_DATE'])
    fpa['SIN_DOY'], fpa['COS_DOY'] = sin, cos
    fpa['CAUSE_CLASS'] = pd.Categorical(fpa.NWCG_CAUSE_CLASSIFICATION.astype(str).map(FPA_CAUSE_MAP).fillna('Missing'),
                                        categories=CAUSE_CATEGORIES)
    # FPA_OWNER_MAP keys are upper-cased OWNER_DESCR values; anything unmapped (there is none in practice, since
    # normalize_owner()'s upper-casing plus this map cover every OWNER_DESCR level) falls back to 'Other',
    # matching analysis.large_fire's own OWNER6 fallback.
    fpa['OWNER_CLASS'] = pd.Categorical(fpa.OWNER_DESCR.astype(str).str.upper().map(FPA_OWNER_MAP).fillna('Other'),
                                        categories=OWNER_CATEGORIES)
    fpa['MONTH'] = fpa['DISCOVERY_DATE'].dt.month.astype(np.int16)
    fpa['LARGE'] = (fpa['FIRE_SIZE'] >= LARGE_ACRES).astype(np.int8)
    fpa['CELL'] = (np.floor(fpa['LATITUDE']).astype(int).astype(str) + '_'
                  + np.floor(fpa['LONGITUDE']).astype(int).astype(str))
    fpa['YEAR'] = fpa['FIRE_YEAR']
    return fpa[['YEAR', 'MONTH', 'CELL', 'LATITUDE', 'LONGITUDE', 'SIN_DOY', 'COS_DOY', 'CAUSE_CLASS',
               'OWNER_CLASS', 'LARGE']].reset_index(drop=True)


def _build_wfigs_features(clean: pd.DataFrame) -> pd.DataFrame:
    wf = clean[clean['size_acres'].notna()].copy()
    wf = wf[~wf['state'].isin(NON_CONUS)].copy()
    wf['CAUSE_CLASS'] = pd.Categorical(wf['cause_class'], categories=CAUSE_CATEGORIES)
    wf['OWNER_CLASS'] = pd.Categorical(wf['owner_class'], categories=OWNER_CATEGORIES)
    wf['LARGE'] = (wf['size_acres'] >= LARGE_ACRES).astype(np.int8)
    wf['YEAR'] = wf['year'].astype(int)
    wf = wf.rename(columns={'latitude': 'LATITUDE', 'longitude': 'LONGITUDE', 'sin_doy': 'SIN_DOY',
                            'cos_doy': 'COS_DOY', 'month': 'MONTH', 'cell': 'CELL'})
    wf = wf.dropna(subset=['LATITUDE', 'LONGITUDE', 'CELL'])
    return wf[['YEAR', 'MONTH', 'CELL', 'LATITUDE', 'LONGITUDE', 'SIN_DOY', 'COS_DOY', 'CAUSE_CLASS',
              'OWNER_CLASS', 'LARGE']].reset_index(drop=True)


def _top_decile_capture(y: np.ndarray, p: np.ndarray, seed: int = 42) -> float:
    """Share of positives captured in exactly the top 10% of rows by score, ties broken by a fixed-seed
    random draw so the 10% cut is exact rather than however many rows share the boundary score."""
    rng = np.random.default_rng(seed)
    tiebreak = rng.random(len(p))
    order = np.lexsort((tiebreak, -p))  # primary: -p descending; secondary: random
    k = int(round(0.1 * len(p)))
    top_idx = order[:k]
    pos = float(y.sum())
    return float(y[top_idx].sum() / pos) if pos > 0 else float('nan')


def _bootstrap_pr_auc(y: np.ndarray, p: np.ndarray, n_boot: int = 1000, seed: int = 42) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    n = len(y)
    vals = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        yb, pb = y[idx], p[idx]
        vals[i] = average_precision_score(yb, pb) if yb.sum() > 0 and yb.sum() < n else np.nan
    return {'low': float(np.nanpercentile(vals, 2.5)), 'high': float(np.nanpercentile(vals, 97.5)), 'n_boot': n_boot}


def run_forward_test(clean: pd.DataFrame) -> dict[str, Any]:
    train = _build_fpa_features()
    test = _build_wfigs_features(clean)
    log.info(f'forward test: training on {len(train):,} FPA FOD 2010-2020 CONUS fires, testing on '
            f'{len(test):,} WFIGS 2021-2025 CONUS fires with a size')

    model = HistGradientBoostingClassifier(categorical_features='from_dtype', **HGB_PARAMS)
    X_train = train[REDUCED_FEATURES].copy()
    for c in REDUCED_CATEGORICAL:
        X_train[c] = X_train[c].astype('category')
    model.fit(X_train, train['LARGE'])

    X_test = test[REDUCED_FEATURES].copy()
    for c in REDUCED_CATEGORICAL:
        X_test[c] = X_test[c].astype('category')
    p_model = model.predict_proba(X_test)[:, 1]

    p_clim = climatology(train[['CELL', 'MONTH', 'LARGE']], test[['CELL', 'MONTH', 'LARGE']], 'LARGE')

    y_test = test['LARGE'].to_numpy()
    base_rate_train = float(train['LARGE'].mean())
    base_rate_test = float(test['LARGE'].mean())

    def _score(p: np.ndarray) -> dict[str, Any]:
        brier = float(np.mean((p - y_test) ** 2))
        brier_base = float(np.mean((base_rate_train - y_test) ** 2))
        return {
            'n': int(len(y_test)), 'n_positive': int(y_test.sum()),
            'pr_auc': float(average_precision_score(y_test, p)),
            'roc_auc': float(roc_auc_score(y_test, p)) if 0 < y_test.sum() < len(y_test) else None,
            'base_rate_test': base_rate_test, 'base_rate_train': base_rate_train,
            'top_decile_capture': _top_decile_capture(y_test, p),
            'brier': brier, 'brier_skill_vs_train_base_rate': 1 - brier / brier_base if brier_base > 0 else None,
        }

    overall = {'model_hgb_reduced': _score(p_model), 'lookup_cell_month_climatology': _score(p_clim)}

    per_year: dict[int, Any] = {}
    for yr in sorted(test['YEAR'].unique()):
        m = (test['YEAR'] == yr).to_numpy()
        yy = y_test[m]
        if yy.sum() == 0 or yy.sum() == len(yy):
            per_year[int(yr)] = {'n': int(len(yy)), 'n_positive': int(yy.sum()), 'note': 'skipped: no variation'}
            continue
        per_year[int(yr)] = {
            'n': int(len(yy)), 'n_positive': int(yy.sum()), 'base_rate_test': float(yy.mean()),
            'model_hgb_reduced': {'pr_auc': float(average_precision_score(yy, p_model[m])),
                                  'roc_auc': float(roc_auc_score(yy, p_model[m])),
                                  'top_decile_capture': _top_decile_capture(yy, p_model[m])},
            'lookup_cell_month_climatology': {'pr_auc': float(average_precision_score(yy, p_clim[m])),
                                              'roc_auc': float(roc_auc_score(yy, p_clim[m])),
                                              'top_decile_capture': _top_decile_capture(yy, p_clim[m])},
        }

    boot = {'model_hgb_reduced': _bootstrap_pr_auc(y_test, p_model),
           'lookup_cell_month_climatology': _bootstrap_pr_auc(y_test, p_clim)}

    os.makedirs(os.path.dirname(MODEL_OUT_PATH), exist_ok=True)
    joblib.dump(model, MODEL_OUT_PATH)
    log.info(f'saved reduced model to {MODEL_OUT_PATH}')

    return {
        'features': REDUCED_FEATURES, 'categorical_features': REDUCED_CATEGORICAL,
        'hgb_params': HGB_PARAMS, 'label_definition': f'final size >= {LARGE_ACRES:.0f} acres',
        'train_definition': 'FPA FOD 2010-2020, CONUS only (AK, HI, PR excluded)',
        'test_definition': 'WFIGS 2021-2025, IncidentTypeCategory=WF, CONUS only, rows with a size',
        'n_train': int(len(train)), 'n_test': int(len(test)),
        'overall': overall, 'per_year': per_year, 'bootstrap_pr_auc_95ci_1000_resamples': boot,
        'model_path': os.path.relpath(MODEL_OUT_PATH, REPO_ROOT),
        'cause_class_categories': CAUSE_CATEGORIES, 'owner_class_categories': OWNER_CATEGORIES,
        'cause_class_definition_fpa_side': 'NWCG_CAUSE_CLASSIFICATION -> Human / Natural / Missing '
                                          '(analysis.large_fire.CAUSE_MAP)',
        'cause_class_definition_wfigs_side': CAUSE_CLASS_DEFINITION,
        'owner_class_definition_fpa_side': 'OWNER_DESCR -> Federal/State/Private/Tribal/Other/Missing '
                                           '(analysis.large_fire.OWNER_MAP)',
        'owner_class_definition_wfigs_side': WFIGS_OWNER_DEFINITION,
    }


def register_forward_test_claims(ft: dict[str, Any]) -> None:
    claim('wfigs.forward_test', ft,
         'Forward test of a reduced-feature HistGradientBoostingClassifier (trained on FPA FOD 2010-2020 '
         'CONUS) against the cell x month climatology lookup, both evaluated on WFIGS 2021-2025 CONUS fires '
         'with a size. PR-AUC, ROC-AUC, base rates, top-10%-by-rank capture, Brier skill vs the training base '
         'rate, per year, plus 1,000-resample bootstrap 95% intervals on PR-AUC for both scorers.',
         n=ft['n_test'])
    m = ft['overall']['model_hgb_reduced']
    lk = ft['overall']['lookup_cell_month_climatology']
    claim('wfigs.forward_test_note',
         "This is a reduced-feature model: only location, day-of-year, a coarse cause class, a coarse owner "
         "class and month are available on both datasets, so it has none of the weather, fuels, terrain or "
         "protection-status features the full large-fire model (analysis/large_fire.py, outputs/claims_model.json) "
         "uses to reach its published accuracy. It is also being scored on WFIGS, a different reporting system "
         "from the FPA FOD data it was trained on (see wfigs.comparability_verdict), with its own size field, "
         "cause coding and coverage. Its PR-AUC here is therefore a lower bound on what the full model would do "
         "on new discoveries, not a test of the full model itself, and the two numbers should never be shown "
         f"side by side as if they measured the same thing. On this forward test the pre-specified reduced model "
         f"scores below the simple cell x month lookup (PR-AUC {m['pr_auc']:.3f} against {lk['pr_auc']:.3f}, "
         f"in every one of the five years), the opposite of the full model's result against the same lookup on "
         "its own 2019-2020 holdout. A diagnostic run after seeing this result (wfigs.forward_test_ablation) "
         "locates the cause in the owner-class feature: 41% of FPA FOD 2010-2020 training fires have no owner "
         "recorded and those rarely become large, while WFIGS records an owner for almost every fire, so the "
         "model's owner rule does not transfer. Without the owner feature, the same model on location and season "
         "(with or without cause) beats the lookup on WFIGS. The diagnostic was chosen after seeing the test "
         "result, so it is evidence about why the pre-specified model failed, not a clean forward test of a new "
         "model. The general lesson stands: features that record how a reporting system codes a fire do not "
         "carry across to another system.",
         'Plain-language caveat for the forward-test numbers.', n=None)


# --------------------------------------------------------------------------- diagnostic (post hoc)

ABLATIONS = {
    'location_season': ['LATITUDE', 'LONGITUDE', 'SIN_DOY', 'COS_DOY', 'MONTH'],
    'location_season_cause': ['LATITUDE', 'LONGITUDE', 'SIN_DOY', 'COS_DOY', 'MONTH', 'CAUSE_CLASS'],
    'location_season_cause_owner': REDUCED_FEATURES,
}


def run_ablation_diagnostic(clean: pd.DataFrame) -> dict[str, Any]:
    """Post hoc: which of the reduced model's features fail to transfer from FPA FOD to WFIGS.

    Each feature set is fitted twice with the same settings: on FPA FOD 2010-2018 and scored on FPA FOD
    2019-2020 (same system, forward in time), and on FPA FOD 2010-2020 and scored on WFIGS 2021-2025 (other
    system). The lookup is scored the same two ways. Added after the pre-specified forward test failed.
    """
    train = _build_fpa_features()
    test = _build_wfigs_features(clean)
    dev, hold = train[train['YEAR'] <= 2018], train[train['YEAR'] >= 2019]

    def fit(X: pd.DataFrame, y: pd.Series) -> HistGradientBoostingClassifier:
        m = HistGradientBoostingClassifier(categorical_features='from_dtype', **HGB_PARAMS)
        m.fit(X, y)
        return m

    def score(y: np.ndarray, p: np.ndarray, boot: bool = False) -> dict[str, Any]:
        out = {'pr_auc': float(average_precision_score(y, p)), 'roc_auc': float(roc_auc_score(y, p)),
               'top_decile_capture': _top_decile_capture(y, p), 'n': int(len(y)), 'n_positive': int(y.sum())}
        if boot:
            out['pr_auc_95ci'] = _bootstrap_pr_auc(y, p)
        return out

    res: dict[str, Any] = {}
    for name, feats in ABLATIONS.items():
        m1 = fit(dev[feats], dev['LARGE'])
        m2 = fit(train[feats], train['LARGE'])
        res[name] = {'features': feats,
                     'fpa_fod_2019_2020': score(hold['LARGE'].to_numpy(), m1.predict_proba(hold[feats])[:, 1]),
                     'wfigs_2021_2025': score(test['LARGE'].to_numpy(), m2.predict_proba(test[feats])[:, 1], boot=True)}
        log.info(f'ablation {name}: FPA {res[name]["fpa_fod_2019_2020"]["pr_auc"]:.3f}, WFIGS {res[name]["wfigs_2021_2025"]["pr_auc"]:.3f}')
    cols = ['CELL', 'MONTH', 'LARGE']
    res['lookup_cell_month'] = {
        'fpa_fod_2019_2020': score(hold['LARGE'].to_numpy(), climatology(dev[cols], hold[cols], 'LARGE')),
        'wfigs_2021_2025': score(test['LARGE'].to_numpy(), climatology(train[cols], test[cols], 'LARGE'), boot=True)}
    res['owner_class_share'] = {'fpa_fod_2010_2020': train['OWNER_CLASS'].value_counts(normalize=True).round(4).to_dict(),
                                'wfigs_2021_2025': test['OWNER_CLASS'].value_counts(normalize=True).round(4).to_dict()}
    res['large_rate_by_owner_class'] = {
        'fpa_fod_2010_2020': train.groupby('OWNER_CLASS', observed=True)['LARGE'].mean().round(4).to_dict(),
        'wfigs_2021_2025': test.groupby('OWNER_CLASS', observed=True)['LARGE'].mean().round(4).to_dict()}
    res['large_rate_by_cause_class'] = {
        'fpa_fod_2010_2020': train.groupby('CAUSE_CLASS', observed=True)['LARGE'].mean().round(4).to_dict(),
        'wfigs_2021_2025': test.groupby('CAUSE_CLASS', observed=True)['LARGE'].mean().round(4).to_dict()}
    return res


def register_ablation_claims(ab: dict[str, Any]) -> None:
    claim('wfigs.forward_test_ablation', ab,
          'POST HOC diagnostic, run after the pre-specified forward test failed: the reduced model refitted with '
          'three feature sets (location+season; +cause; +cause+owner, the pre-specified set), each scored forward '
          'in time on FPA FOD (fit 2010-2018, score 2019-2020) and across systems (fit FPA FOD 2010-2020, score '
          'WFIGS 2021-2025 CONUS), with the cell x month lookup scored the same ways; plus owner-class shares and '
          'large-fire rates by owner and cause class in each system. PR-AUC intervals: 1,000 bootstrap resamples.',
          n=ab['location_season']['wfigs_2021_2025']['n'],
          note='Chosen after seeing the test result; evidence about why the pre-specified model failed, not a '
               'clean forward test of a new model.')


# --------------------------------------------------------------------------- CLI


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--stage', choices=['download', 'analyze', 'all'], default='all')
    ap.add_argument('--out', default=os.path.join(REPO_ROOT, 'outputs'))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')
    t0 = time.time()

    if args.stage in ('download', 'all'):
        stage_download(args.out)

    if args.stage in ('analyze', 'all'):
        if not os.path.exists(PARQUET_PATH):
            raise SystemExit(f'{PARQUET_PATH} not found; run --stage download first')
        clean = pd.read_parquet(PARQUET_PATH)
        with open(MANIFEST_PATH) as f:
            manifest = json.load(f)
        set_source('analysis.wfigs')
        register_descriptive_claims(clean, manifest)
        register_fpa_comparison(clean)
        ft = run_forward_test(clean)
        register_forward_test_claims(ft)
        register_ablation_claims(run_ablation_diagnostic(clean))
        n = write_claims(os.path.join(args.out, 'claims_wfigs.json'))
        log.info(f'wrote {n} claims to {os.path.join(args.out, "claims_wfigs.json")}')

    log.info(f'done in {(time.time() - t0) / 60:.1f} min')
    return 0


if __name__ == '__main__':
    sys.exit(main())
