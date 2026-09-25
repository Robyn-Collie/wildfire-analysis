"""Shared definitions for the analysis package: data loading, regions, size classes, claims.

Every definition that a claim depends on lives here so that the README, the findings
write-up and the site all use the same one.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Any, Iterable

import numpy as np
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARQUET_PATH = os.environ.get('WILDFIRE_PARQUET_PATH', os.path.join(REPO_ROOT, 'data', 'fires.parquet'))

# --------------------------------------------------------------------------- data

def load_fires(columns: Iterable[str] | None = None, path: str = PARQUET_PATH) -> pd.DataFrame:
    """Read data/fires.parquet with a column selection.

    The parquet holds the same 2,303,566 rows as the FPA FOD 6th edition SQLite table
    ``Fires`` plus derived columns (DISCOVERY_DATETIME, CONT_DATETIME, DURATION_DAYS,
    DURATION_HOURS, DISCOVERY_MONTH). Always pass ``columns`` to keep memory low.
    """
    cols = list(columns) if columns is not None else None
    return pd.read_parquet(path, columns=cols)


# --------------------------------------------------------------------------- regions

# The project's own five-plus-one region scheme. These are the lists used by
# scripts/reproduce.py (Phase 0) so that numbers stay comparable.
WEST = ['AZ', 'CA', 'CO', 'ID', 'MT', 'NV', 'NM', 'OR', 'UT', 'WA', 'WY']
SOUTH = ['AL', 'AR', 'FL', 'GA', 'KY', 'LA', 'MS', 'NC', 'OK', 'SC', 'TN', 'TX', 'VA', 'WV']
NORTHEAST = ['CT', 'ME', 'MA', 'NH', 'RI', 'VT', 'NY', 'NJ', 'PA']
ALASKA = ['AK']
ISLANDS = ['HI', 'PR']  # Hawaii and Puerto Rico, kept apart from "Other" because they are not contiguous

REGION_ORDER = ['West', 'South', 'Northeast', 'Alaska', 'Hawaii/PR', 'Other']
REGION_DEFINITION = (
    'West = ' + ' '.join(WEST) + '; South = ' + ' '.join(SOUTH) + '; Northeast = ' + ' '.join(NORTHEAST)
    + '; Alaska = AK; Hawaii/PR = HI PR; Other = every other STATE value (Midwest, Plains, DC, DE, MD).'
)


def region_of(state: pd.Series) -> pd.Series:
    """Map STATE to the project region (see REGION_DEFINITION). Returns a plain object Series."""
    s = state.astype(str)
    out = pd.Series('Other', index=state.index, dtype=object)
    out[s.isin(WEST)] = 'West'
    out[s.isin(SOUTH)] = 'South'
    out[s.isin(NORTHEAST)] = 'Northeast'
    out[s.isin(ALASKA)] = 'Alaska'
    out[s.isin(ISLANDS)] = 'Hawaii/PR'
    return out


# NWCG Geographic Area Coordination Centers (GACCs), approximated at state level.
#
# What was verified in this session (fetched 2026-09-25):
#   - https://gacc.nifc.gov/ names ten GACCs: Alaska, Eastern Area, Great Basin, Northern California,
#     Northern Rockies, Northwest, Rocky Mountain, Southern Area, Southern California, Southwest.
#   - https://gacc.nifc.gov/nwcc/ : Northwest "includes the States of Oregon and Washington".
#   - https://gacc.nifc.gov/swcc/ : Southwest dispatch centers are in Arizona and New Mexico.
#   - https://gacc.nifc.gov/gbcc/ : Great Basin dispatch centers are in Idaho, Nevada, Utah, Wyoming.
#   - https://gacc.nifc.gov/rmcc/ : Rocky Mountain dispatch centers are in Wyoming, Colorado and the Great Plains.
#   - https://gacc.nifc.gov/eacc/ : Eastern Area is a "twenty-state" area (the list itself was not on the page).
# What is NOT verified from a fetched page (assigned from general knowledge and flagged as such):
#   the Southern Area state list, the Eastern Area state list, and the split states.
# Real GACC boundaries do not follow state lines: Idaho and Wyoming are split between Great Basin,
# Northern Rockies and Rocky Mountain; California is split North/South; west Texas is in the Southwest.
# This mapping assigns each whole state to one area and merges the two California GACCs, so it is
# a state-level approximation, not the official boundary.
GACC_STATES: dict[str, list[str]] = {
    'Alaska': ['AK'],
    'Northwest': ['OR', 'WA'],
    'California (North+South merged)': ['CA'],
    'Great Basin (approx)': ['ID', 'NV', 'UT'],
    'Northern Rockies (approx)': ['MT', 'ND'],
    'Rocky Mountain (approx)': ['CO', 'WY', 'SD', 'NE', 'KS'],
    'Southwest': ['AZ', 'NM'],
    'Southern Area (approx)': ['AL', 'AR', 'FL', 'GA', 'KY', 'LA', 'MS', 'NC', 'OK', 'SC', 'TN', 'TX', 'VA', 'PR'],
    'Eastern Area (approx)': ['CT', 'DE', 'DC', 'IA', 'IL', 'IN', 'ME', 'MD', 'MA', 'MI', 'MN', 'MO', 'NH', 'NJ',
                              'NY', 'OH', 'PA', 'RI', 'VT', 'WV', 'WI'],
    'Hawaii (not a GACC)': ['HI'],
}
GACC_DEFINITION = ('State-level approximation of the ten NWCG GACCs; whole states assigned to one area, '
                   'California North/South merged, Idaho and Wyoming not split. Lists: '
                   + '; '.join(f'{k} = {" ".join(v)}' for k, v in GACC_STATES.items()))


def gacc_of(state: pd.Series) -> pd.Series:
    lookup = {st: area for area, states in GACC_STATES.items() for st in states}
    return state.astype(str).map(lookup).fillna('Unassigned')


# --------------------------------------------------------------------------- size classes

SIZE_CLASSES = ['A', 'B', 'C', 'D', 'E', 'F', 'G']
SIZE_CLASS_LABELS = {
    'A': 'A (<0.26 ac)', 'B': 'B (0.26-9.9 ac)', 'C': 'C (10-99.9 ac)', 'D': 'D (100-299 ac)',
    'E': 'E (300-999 ac)', 'F': 'F (1,000-4,999 ac)', 'G': 'G (5,000+ ac)',
}
SIZE_CLASS_DEFINITION = ('FIRE_SIZE_CLASS as coded in FPA FOD: A < 0.26 acres, B 0.26-9.9, C 10-99.9, '
                         'D 100-299, E 300-999, F 1,000-4,999, G 5,000 and up.')

MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

CAUSE_MISSING = 'Missing data/not specified/undetermined'
OWNER_MISSING = 'MISSING/NOT SPECIFIED'


def normalize_owner(owner: pd.Series) -> pd.Series:
    """OWNER_DESCR upper-cased so that 'Private' (2 rows) merges into 'PRIVATE'."""
    return owner.astype(str).str.upper()


# --------------------------------------------------------------------------- claims registry

CLAIMS: dict[str, dict[str, Any]] = {}
_SOURCE = 'analysis.descriptive'


def set_source(name: str) -> None:
    global _SOURCE
    _SOURCE = name


def jsonable(value: Any) -> Any:
    """Convert numpy / pandas objects into plain JSON types."""
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, pd.DataFrame):
        return {str(k): jsonable(v) for k, v in value.to_dict('index').items()}
    if isinstance(value, pd.Series):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        f = float(value)
        return None if np.isnan(f) else f
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, _dt.datetime, _dt.date)):
        return value.isoformat()
    if value is pd.NA or value is pd.NaT:
        return None
    return value


def claim(id: str, value: Any, definition: str, n: int | None, note: str | None = None,
          unit: str | None = None) -> Any:
    """Register a computed number (or small table) with its definition and sample size.

    Returns ``value`` unchanged so a claim can be registered inline.
    """
    if id in CLAIMS:
        raise KeyError(f'duplicate claim id: {id}')
    CLAIMS[id] = {
        'value': jsonable(value),
        'unit': unit,
        'definition': definition,
        'n': None if n is None else int(n),
        'note': note,
        'computed_at': _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat(),
        'source': _SOURCE,
    }
    return value


def write_claims(path: str) -> int:
    """Write the registry to ``path`` (JSON, one object per claim id). Returns the claim count."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(CLAIMS, f, indent=1, sort_keys=True, default=str)
    return len(CLAIMS)
