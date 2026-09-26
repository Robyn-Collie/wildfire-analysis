# Test suite and CI: summary

Author: tests agent (wave 1), updated by the src-fix engineer on branch `fix/src-defects`.
Files written by the tests agent: `tests/conftest.py`, `tests/test_data_loader.py`,
`tests/test_features.py`, `tests/test_train_model.py`, `tests/test_build_cache.py`,
`tests/test_reproduce_helpers.py`, `.github/workflows/ci.yml`, `pytest.ini`, this file.
Added on `fix/src-defects`: `tests/test_download.py`, and the `src/`, `scripts/`,
`run_pipeline.py` and requirements changes described under "Status of the defects" below.

Result on `fix/src-defects`: `.venv/bin/python -m pytest -q` gives 108 passed, 0 xfailed,
0 warnings in about 16 s (pandas 3.0.6, numpy 2.5.3, scikit-learn 1.9.1, pyarrow 25.0.1,
Python 3.12.3). At the tests agent's commit (`f2fce3a`) it was 66 passed, 1 xfailed. Nothing
in the suite depends on `data/`, on the network, or on the caller's environment: the loader
tests use a synthetic SQLite file, the download tests use a local HTTP server.

## Status of the defects (fix/src-defects)

Every defect the original suite pinned with a `_DEFECT` / `_KNOWN_ISSUE` test, plus the
observations and the panel-repro findings assigned to this branch, is fixed. The pinning
tests were flipped to assert the fixed behaviour in the same commit as each fix.

| # | Defect | Fixed in | Test that now asserts the fix |
|---|---|---|---|
| 1 | `load_data` called `sys.exit(1)` and swallowed the exception type | `data_loader: raise instead of sys.exit, select FOD_ID, ORDER BY FOD_ID` | `test_missing_db_raises_file_not_found`, `test_env_pointing_at_missing_db_raises_file_not_found`, `test_unreadable_db_raises_database_error`, `test_db_without_fires_table_raises`, `test_run_pipeline_exits_1_with_help_when_db_missing` |
| 2 | Leap years: DOY divided by a fixed 365, Dec 31 of a leap year encoded as Jan 1 | `features: fixed cause schema, leap-aware DOY angle, ...` | `test_doy_366_does_not_collide_with_doy_1`, `test_doy_366_encodes_as_year_end` (was the xfail), `test_jan_1_is_angle_zero_in_leap_and_non_leap_years`, `test_same_calendar_date_in_leap_and_non_leap_year_is_within_one_day_step`, `test_discovery_doy_column_is_ignored` |
| 3 | One-hot schema drift with the causes present in the batch | same commit | `test_schema_is_fixed_when_a_cause_is_absent`, `test_single_cause_input_still_yields_all_13_cause_columns`, `test_unknown_cause_raises_value_error`, `test_null_cause_raises_value_error`, `test_cause_levels_are_the_13_causes_in_alphabetical_order` |
| 4 | Parallelism hard-coded (`n_jobs=-1` in two places) | `train_model: n_jobs from WILDFIRE_N_JOBS, out_dir, metrics dict and metrics.json` | `test_default_n_jobs_is_1_without_env`, `test_default_n_jobs_reads_env`, `test_default_n_jobs_rejects_bad_values`, `test_build_model_config`, `test_train_model_is_reproducible_and_independent_of_n_jobs` |
| 5 | Plots written to the CWD; metrics only in log lines | same commit | `test_train_model_end_to_end` (out_dir containment, metrics dict, `metrics.json`), `test_train_model_skip_cv`, `test_train_model_default_out_dir_is_outputs_under_repo_root` |
| obs. | Dates parsed by inference | features commit | `test_iso_or_day_first_dates_raise_instead_of_being_guessed` |
| obs. | NaN duration dropped and logged as "negative" | features commit | `test_missing_containment_date_raises_not_dropped_as_negative`, `test_nan_and_negative_durations_are_counted_separately` |
| C2 | `fillna(0)` would put a fire with no coordinates at 0 N 0 E | features commit | `test_missing_coordinate_raises_instead_of_becoming_zero` |
| C12 | Features chosen by blacklist | features commit | `test_extra_input_columns_never_leak_into_x`, `test_missing_required_column_raises_key_error`, `test_x_has_exactly_the_17_reported_features` (asserts `FEATURE_COLUMNS`) |
| D5 | Row order depended on SQLite physical order | data_loader commit (`ORDER BY FOD_ID`, `FOD_ID` selected) | `test_load_data_orders_by_fod_id_not_physical_row_order`, `test_load_data_selects_exactly_the_model_columns` |
| D7 | `run_pipeline.py` imported `src/` modules under bare names | data_loader commit | covered by `test_run_pipeline_exits_1_with_help_when_db_missing` (runs the script) |
| P1-P4 | Download script: no checksum, truncated zip reused, no resume/retry/timeout/UA, member by suffix, no disk check | `download_data: verified, resumable download with exact member and disk checks` | `tests/test_download.py` (15 tests) |
| D1, D3 | `pyarrow`, `duckdb` unpinned; lock stale; Python version inconsistent | `requirements: pin pyarrow and duckdb, regenerate the lock from the venv` | none (a CI install from `requirements.txt` is the check) |

Two consequences for the reported numbers, both logged in `docs/EXPERIMENTS.md` E-009: the
leap-aware angle changes the model inputs for the 27% of rows in leap years, and
`ORDER BY FOD_ID` changes the row order the position-based `train_test_split` shuffles, so
the random split itself is different from E-001's. Neither the model, the split method nor
the seed changed.

Not fixed on this branch (out of its scope): schema and hash validation inside `load_data`
(panel-repro C8), `int8` dummies (C13), `reproduce.py` calling `train_model` instead of
re-implementing the split (C10, second half), the `analysis/` package layout (D7 in full),
the `.gitignore` change for committed outputs (P6), and the notebook (N1-N4).

## How to run

```
.venv/bin/python -m pytest -q          # from the repo root; pytest.ini sets testpaths and pythonpath
.venv/bin/ruff check --select E9,F63,F7,F82 src scripts tests run_pipeline.py   # the CI lint step
```

## The fixture (tests/conftest.py)

The real database is 1 GB and never leaves `data/`. Every test runs against a synthetic
SQLite file built once per session in a pytest temp dir and exposed two ways: the
`synthetic_db_path` fixture, and the `WILDFIRE_DB_PATH` environment variable set by an
autouse `monkeypatch` fixture, so `load_data()` with no argument also hits the synthetic file.
`synthetic_rows` returns the frame that was written (ground truth, indexed by FOD_ID) and
`loaded_df` returns what `load_data` produces for it.

Shape of the synthetic `Fires` table, checked against the real file with `PRAGMA table_info`
and `SELECT ... LIMIT 3`:

| Property | Synthetic | Real file |
|---|---|---|
| Columns | the 32 named in the brief, same declared types (`int32`, `text(255)`, `float64`, ...) plus an `OBJECTID INTEGER PRIMARY KEY` | same, plus `Shape` (geometry) and 7 SOURCE_/LOCAL_/FIRE_CODE columns nothing here reads |
| Rows | 300, deterministic (`numpy.random.default_rng(20221014)`) | 2,303,566 |
| Years | 2005-2020, cycling | 1992-2020 |
| Date text | unpadded `M/D/YYYY` such as `2/2/2005` | unpadded `M/D/YYYY` (observed `2/2/2005`, `5/12/2004`) |
| Time text | zero-padded `HHMM` | zero-padded `HHMM` (observed `0845`, `1300`) |
| Causes | all 13 NWCG_GENERAL_CAUSE values, each also present in the 2010+ / CONT_DATE-not-null subset | 13 values |
| Size classes | A through G, from a log-uniform FIRE_SIZE 0.01 to about 31,600 acres | A through G |

Note on the brief: it describes the dates as `MM/DD/YYYY`. The real file is not zero-padded.
Both forms parse under `format='%m/%d/%Y'`, and the synthetic rows follow the real file.

Planted edge cases (row ids are constants in `conftest.py`, used by name in the tests):

| Constant | FOD_ID | What |
|---|---|---|
| `KNOWN_ROW_2006` | 1001 | 3/1/2006 08:30 to 3/3/2006 14:15: 2 days, 53.75 h (below the 2010 cutoff) |
| `KNOWN_ROW_2010` | 1021 | 6/15/2010 14:00 to 6/20/2010 09:00: 5 days, 115 h |
| `NEGATIVE_DURATION_ID` | 1005 | CONT_DATE two days before DISCOVERY_DATE, FIRE_YEAR 2010 |
| `INVALID_TIME_ID` | 1012 | DISCOVERY_TIME `2560` (hour 25) |
| `MISSING_DISC_TIME_ID` | 1013 | DISCOVERY_TIME NULL |
| `MISSING_CONT_TIME_ID` | 1006 | CONT_TIME NULL |
| `MISSING_CONT_DATE_ID` | 1007 | CONT_DATE NULL (FIRE_YEAR 2012) |
| (pattern) | every 10th row from 1007 | CONT_DATE NULL (30 rows) |
| (pattern) | every 24th row from 1003 | Dec 31 of a leap year, DISCOVERY_DOY 366 (13 rows) |
| (pattern) | every 9th / 11th row | DISCOVERY_TIME / CONT_TIME NULL |

The generator asserts its own invariants (all 13 causes survive the loader's filter, at least
five DOY-366 rows, all seven size classes) so a future edit to the generator cannot silently
weaken the tests.

## What is covered

| File | Tests | Covers |
|---|---|---|
| `test_data_loader.py` | 12 | filter is exactly `FIRE_YEAR >= 2010 AND CONT_DATE IS NOT NULL`; the 9 selected columns (FOD_ID first); rows come back ordered by FOD_ID even when inserted in reverse; dates arrive as text; `WILDFIRE_DB_PATH` is honoured; an explicit path overrides the env var; missing file and env var to a missing file raise `FileNotFoundError` carrying the help text; a non-database file raises a database error; a database without `Fires` raises; `run_pipeline.py` exits 1 with the help text and no traceback |
| `test_features.py` | 33 | DURATION_DAYS = CONT - DISCOVERY in whole days (hand-built rows and every synthetic row, including the 400-day tail), int64; negative rows dropped with exactly one WARNING on logger `src.features`, no warning otherwise; NaN durations raise and are not counted as negative; SIN/COS in [-1, 1] and on the unit circle; day 1 vs day 365 one day apart, day 1 vs day 183 nearly opposite; Jan 1 is angle 0 in leap and non-leap years; Dec 31 of a leap year is one day step before Jan 1 and within 5e-5 rad of Dec 31 of a non-leap year; Mar 1 2019 vs Mar 1 2020 within one day step; `DISCOVERY_DOY` is ignored; `CAUSE_LEVELS` is the 13 causes alphabetically; all 13 `CAUSE_*` columns, one-hot exactly one per row; the schema is the same 17 columns when a cause is absent or only one cause is present; unknown and null causes raise; ISO and day-first dates raise; missing coordinates raise; X is exactly `FEATURE_COLUMNS`; extra input columns never reach X; a missing required column raises `KeyError`; X excludes FOD_ID, FIRE_YEAR, FIRE_SIZE_CLASS, both dates, DOY, the target and the raw cause; no NaNs; y shares X's index and keeps original labels; the input frame is not mutated |
| `test_train_model.py` | 16 | `split_data` deterministic, 80/20, disjoint, equal to `train_test_split(..., random_state=42)`; `default_n_jobs()` is 1 without `WILDFIRE_N_JOBS`, reads it (1, 2, -1, padded), rejects 0 / non-integers; `build_model` is 100 trees, depth 10, random_state 42, n_jobs 1 by default and overridable; `train_model(X, y, out_dir=...)` end to end from a foreign CWD returns a fitted 100-tree forest with `feature_names_in_ == FEATURE_COLUMNS`, non-negative finite predictions, a metrics dict (n_rows/train/test, features, config, test RMSE/MAE recomputed, 5 CV folds with mean and std) equal to `metrics.json`, both PNGs in `out_dir` and nothing in the CWD; `skip_cv` omits the CV keys; default `out_dir` is `outputs/` under the repo root; two runs give identical predictions and `n_jobs=2` agrees to 1e-12 |
| `test_download.py` | 15 | against a local Range-capable HTTP server: download, extract, verify, zip removed, no `.part` left; `User-Agent` and `timeout` sent; nothing to do when the DB exists; a `.part` is resumed with `Range: bytes=N-`; a complete `.part` is accepted via 416; a mid-body disconnect is retried and resumed rather than restarted; a server whose Content-Length exceeds what it sends never gets its `.part` renamed and exits 1 after 3 attempts; an unreachable server exits 1; a hash mismatch exits 2, moves the file to `.unverified`, keeps the zip and prints both hashes; the real `data.sha256` parses; the member is chosen by exact name (`Data/FPA_FOD_20221014.sqlite`), a decoy `.sqlite` earlier in the archive is ignored, a missing member exits 1; insufficient disk space aborts before the download and before the extraction |
| `test_build_cache.py` | 11 | `build(db_path, cache_path)` writes all 300 rows with the derived columns; dtypes (datetime64, category with the 13 causes, Int8 month); exact DURATION_DAYS / DURATION_HOURS / DISCOVERY_DATETIME for the known rows; DURATION_DAYS matches ground truth for every row including NaN where CONT_DATE is NULL; NaT and NaN hours when a time is NULL or invalid (`2560`) while the day-level duration survives; the negative row is kept (the cache does not filter); `db_sha256` metadata equals the file hash; second call is a no-op ("is up to date", mtime and size unchanged); a stale hash triggers a rebuild; `parse_datetime` directly |
| `test_reproduce_helpers.py` | 23 | `to_datetime` with and without times (valid, whitespace, NULL, empty, hour 24/25, minute 60, 3 and 5 digit strings, letters, missing date), index preserved; `metrics` rmse/mae on known errors, zero on perfect prediction, sign symmetric, "predict 0" MAE equals the target mean; `pct_better` sign convention including the README's 7.05 comparison; `region_of` for all four regions plus Other and NULL, index preserved; the region lists are disjoint, exclude AK, and have 11/14/9 members |

Not covered, on purpose: the success path of `run_pipeline.py` (it only chains the three
functions and would need the real database; its failure path is tested), the real network
in `scripts/download_data.py` (the local server stands in for it), and the Part 1/2 bodies
of `scripts/reproduce.py` (`run_model`, `run_sample_checks`, `run_descriptive` need the real
data and several minutes). The helpers those bodies rely on are covered.

## Defects the tests documented at `f2fce3a` (all fixed on `fix/src-defects`, see the status table above)

Kept as the record of what was found. Each was pinned by a test whose name ended in
`_DEFECT` or `_KNOWN_ISSUE`; those tests were flipped to the fixed behaviour in the commit
that fixed them, and the names in this section are the original ones.

1. `load_data` calls `sys.exit(1)` instead of raising (`src/data_loader.py:39` for a
   missing file, `:72` for any other error, which also swallows the original exception
   type). A library function that exits the interpreter cannot be used from a notebook, a
   test, or a script that wants to fall back to the Parquet cache. Tests:
   `test_missing_db_raises_systemexit_DEFECT`, `test_env_pointing_at_missing_db_raises_systemexit_DEFECT`,
   `test_unreadable_db_raises_systemexit_DEFECT`.
2. Leap years in the cyclical encoding (`src/features.py:45-46`): DOY is divided by a fixed
   365, so Dec 31 of a leap year (DOY 366) is encoded at exactly the same angle as Jan 1, and
   every leap-year date after Feb 28 is one day off relative to the same calendar date in a
   non-leap year. Tests: `test_doy_366_collides_with_doy_1_KNOWN_ISSUE` (pins current),
   `test_doy_366_encodes_as_year_end_EXPECTED_FIX` (xfail, strict=False, passes after the fix).
   Effect on the reported numbers is expected to be tiny (a 1/365 rotation on about a quarter
   of rows) but it does change model inputs, so the fix needs a reproduce run and an
   EXPERIMENTS.md entry.
3. Inference-time schema drift (`src/features.py:52`): `pd.get_dummies` derives the columns
   from the categories present in the batch. A batch missing one cause yields 16 columns
   instead of 17 and a fitted model rejects it; a batch with a new or renamed cause value
   silently adds a column. Tests: `test_schema_drift_when_a_cause_is_absent_DEFECT`,
   `test_single_cause_input_yields_single_cause_column_DEFECT`.
4. Parallelism is hard-coded (`src/train_model.py:45` `build_model()` with its `n_jobs=-1`
   default, `:53` `cross_val_score(..., n_jobs=-1)`). On the shared 4-CPU box this violates
   the project's own n_jobs=1 rule and the tests have to monkeypatch two module attributes to
   run safely. Fixture: `single_core` in `test_train_model.py`.
5. Output location is the process CWD (`src/train_model.py:103` and `:130` write
   `residuals.png` and `feature_importance.png` relative to wherever Python was started).
   The tests `chdir` into `tmp_path` to contain this. Test: `test_train_model_end_to_end_single_core`.

Observations that are not defects but worth knowing:

- `src/features.py:26-27` parse dates with no `format=`; pandas infers `%m/%d/%Y` from the
  first row, which works for this file, but an explicit format is both faster on 630k rows and
  immune to a first row like `1/2/2010` being read day-first if a default ever changes.
- `src/features.py:36` (`df['DURATION_DAYS'] >= 0`) would also silently drop rows whose
  duration is NaN. That cannot happen today because `load_data` filters `CONT_DATE IS NOT NULL`,
  but `preprocess_data` on the Parquet cache (which keeps those rows) would drop them without
  the "negative duration" warning being accurate.
- `scripts/build_cache.py` keeps the negative-duration row (the tests assert this). That is the
  right behaviour for a cache; consumers filter.

## Recommended changes to src/ (exact, file:line, before / after)

These were proposals at `f2fce3a`; all of them are implemented on `fix/src-defects`, with
two departures: the leap-year angle is `2*pi*(DOY-1)/days_in_year` from `DISCOVERY_DATE`
(Jan 1 at angle 0, so the xfail test was rewritten for that convention rather than for
"Dec 31 at sin 0, cos 1"), and the `n_jobs` default is 1 from `WILDFIRE_N_JOBS` rather than
keeping -1. The text below is unchanged.

### src/data_loader.py

Line 3, remove the now-unused import once the two `sys.exit` calls are gone:

```
before:  import sys
after:   (delete the line)
```

Lines 34-39:

```
before:
    if not os.path.exists(db_path):
        logger.error(f"Database not found at '{db_path}'.")
        logger.error(f"Run 'python scripts/download_data.py' to put '{DB_FILENAME}' in the 'data' directory,")
        logger.error("or set WILDFIRE_DB_PATH to its location.")
        logger.error("Source: USDA Forest Service, FPA FOD 6th edition (doi:10.2737/RDS-2013-0009.6)")
        sys.exit(1)
after:
    if not os.path.exists(db_path):
        raise FileNotFoundError(
            f"Database not found at '{db_path}'. Run 'python scripts/download_data.py' to put "
            f"'{DB_FILENAME}' in the 'data' directory, or set WILDFIRE_DB_PATH to its location. "
            "Source: USDA Forest Service, FPA FOD 6th edition (doi:10.2737/RDS-2013-0009.6)")
```

Lines 43-72, drop the blanket `try/except ... sys.exit(1)` and let `sqlite3`/pandas errors
propagate (keep the `with` so the connection closes on error):

```
before:
    try:
        conn = sqlite3.connect(db_path)
        ...
        df = pd.read_sql_query(query, conn)
        conn.close()
        logger.info(f"Successfully loaded {len(df)} records.")
        return df
    except Exception as e:
        logger.error(f"An error occurred while loading data: {e}")
        sys.exit(1)
after:
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(query, conn)
    logger.info(f"Successfully loaded {len(df)} records.")
    return df
```

Then in `run_pipeline.py:32` (the only CLI caller) wrap `load_data()` in
`try/except FileNotFoundError as e: logger.error(e); sys.exit(1)` so the command-line
behaviour is unchanged. After this change, flip the three `_DEFECT` tests in
`test_data_loader.py` to `pytest.raises(FileNotFoundError)` and `pytest.raises(sqlite3.DatabaseError)`.

### src/features.py

Lines 26-27, explicit format:

```
before:
    df['DISCOVERY_DATE'] = pd.to_datetime(df['DISCOVERY_DATE'])
    df['CONT_DATE'] = pd.to_datetime(df['CONT_DATE'])
after:
    df['DISCOVERY_DATE'] = pd.to_datetime(df['DISCOVERY_DATE'], format='%m/%d/%Y')
    df['CONT_DATE'] = pd.to_datetime(df['CONT_DATE'], format='%m/%d/%Y')
```

Lines 45-46, leap-year-aware period (DISCOVERY_DATE is already datetime at this point and
FIRE_YEAR has not been dropped yet):

```
before:
    df['SIN_DOY'] = np.sin(2 * np.pi * df['DISCOVERY_DOY'] / 365)
    df['COS_DOY'] = np.cos(2 * np.pi * df['DISCOVERY_DOY'] / 365)
after:
    days_in_year = np.where(df['DISCOVERY_DATE'].dt.is_leap_year, 366, 365)
    df['SIN_DOY'] = np.sin(2 * np.pi * df['DISCOVERY_DOY'] / days_in_year)
    df['COS_DOY'] = np.cos(2 * np.pi * df['DISCOVERY_DOY'] / days_in_year)
```

This changes model inputs, so re-run `scripts/reproduce.py --part model` and record the
before/after in `docs/EXPERIMENTS.md`. After the change, `test_doy_366_encodes_as_year_end_EXPECTED_FIX`
passes and `test_doy_366_collides_with_doy_1_KNOWN_ISSUE` must be deleted.

Line 52, fixed category list so the feature matrix is the same 17 columns for any batch.
Add a module constant (the list is alphabetical, which is the order `get_dummies` already
produces, so the reported numbers do not move):

```
before:
    df = pd.get_dummies(df, columns=['NWCG_GENERAL_CAUSE'], prefix='CAUSE')
after:
    CAUSES = [  # module level, all 13 NWCG_GENERAL_CAUSE values in the FPA FOD 6th edition
        'Arson/incendiarism', 'Debris and open burning', 'Equipment and vehicle use',
        'Firearms and explosives use', 'Fireworks', 'Missing data/not specified/undetermined',
        'Misuse of fire by a minor', 'Natural', 'Other causes',
        'Power generation/transmission/distribution', 'Railroad operations and maintenance',
        'Recreation and ceremony', 'Smoking']
    ...
    unknown = set(df['NWCG_GENERAL_CAUSE'].dropna()) - set(CAUSES)
    if unknown:
        raise ValueError(f'Unknown NWCG_GENERAL_CAUSE values: {sorted(unknown)}')
    df['NWCG_GENERAL_CAUSE'] = pd.Categorical(df['NWCG_GENERAL_CAUSE'], categories=CAUSES)
    df = pd.get_dummies(df, columns=['NWCG_GENERAL_CAUSE'], prefix='CAUSE')
```

After the change, `test_schema_drift_when_a_cause_is_absent_DEFECT` should assert
`sub_X.shape[1] == 17` and `test_single_cause_input_yields_single_cause_column_DEFECT` should
assert all 13 cause columns exist with 12 of them all-zero.

### src/train_model.py

Line 30 and 45 and 53, make parallelism a parameter (default keeps current behaviour):

```
before (30):  def train_model(X: pd.DataFrame, y: pd.Series) -> RandomForestRegressor:
after  (30):  def train_model(X: pd.DataFrame, y: pd.Series, n_jobs: int = -1,
                              out_dir: str = '.') -> RandomForestRegressor:
before (45):      rf = build_model()
after  (45):      rf = build_model(n_jobs=n_jobs)
before (53):      cv_scores = cross_val_score(rf, X_train, y_train, cv=kf, scoring='neg_root_mean_squared_error', n_jobs=-1)
after  (53):      cv_scores = cross_val_score(rf, X_train, y_train, cv=kf, scoring='neg_root_mean_squared_error', n_jobs=n_jobs)
```

Lines 76-77, 81, 103, 108, 130, thread `out_dir` through the two plot helpers:

```
before (76-77):
    plot_feature_importance(rf, X.columns)
    plot_residuals(y_test, y_pred)
after:
    plot_feature_importance(rf, X.columns, out_dir)
    plot_residuals(y_test, y_pred, out_dir)
before (103):  output_path = 'residuals.png'
after  (103):  output_path = os.path.join(out_dir, 'residuals.png')
before (130):  output_path = 'feature_importance.png'
after  (130):  output_path = os.path.join(out_dir, 'feature_importance.png')
```

(and `import os` at the top, and `out_dir: str = '.'` on both helper signatures). After the
change, the `single_core` fixture in `test_train_model.py` can be replaced by
`tm.train_model(X, y, n_jobs=1, out_dir=str(tmp_path))` and the `chdir` removed.

## CI (.github/workflows/ci.yml)

- Triggers on `push` and `pull_request`; `ubuntu-latest`; `actions/setup-python@v5` with
  Python 3.12 and a pip cache keyed on `requirements.txt`; `MPLBACKEND=Agg` at job level.
- Installs `-r requirements.txt` plus `pytest pyarrow ruff` (unchanged `requirements.txt`).
- Lint step: `ruff check --select E9,F63,F7,F82 src scripts tests run_pipeline.py`. Only
  syntax errors, invalid comparisons, misplaced control flow and undefined names fail the
  build; style does not. It passes today (also passes on `.` including the notebook).
- Test step: `python -m pytest -q`.

Pin check for `ubuntu-latest` (Python 3.12, x86_64, glibc 2.39): I queried
`https://pypi.org/pypi/<name>/<version>/json` for each line of `requirements.txt` in this
session. Every pin has a `cp312` `manylinux_2_28` (or `py3-none-any`) wheel:
pandas 3.0.6, numpy 2.5.3, scikit-learn 1.9.1, scipy 1.18.1, matplotlib 3.11.2, seaborn 0.13.2,
ipykernel 7.3.0. A clean `uv venv` install of that set plus pytest/pyarrow/ruff resolved and
ran the suite green on this box. I could not run the workflow on GitHub from here, so the
first real push is the final check; nothing in the pins suggests it will fail. Note that
`ipykernel` (and its Jupyter dependencies) is installed by CI only because it is in
`requirements.txt`; it is not needed by the tests and adds a little install time. Not changed,
per the brief.

## pytest.ini

`testpaths = tests`, `pythonpath = .` (so `src.*` and `scripts.*` import from the repo root
without `sys.path` games; `scripts/` is a namespace package), `-ra --strict-markers`,
`xfail_strict = false`, and `filterwarnings` that show everything by default and silence only
third-party DeprecationWarnings from seaborn, sklearn and matplotlib. The run is warning-free
today. `MPLBACKEND=Agg` is set in `tests/conftest.py` with `os.environ.setdefault` before any
matplotlib import, because pytest.ini cannot set environment variables without a plugin.

## Proposed changes to other files

- `run_pipeline.py:32`: catch `FileNotFoundError` from `load_data()` and exit 1 there (see
  data_loader proposal above). `run_pipeline.py:14` also imports `data_loader` as a top-level
  module by appending `src/` to `sys.path`, which creates a second copy of each module
  (`data_loader` vs `src.data_loader`) when both import styles are used in one process; the
  scripts already use `from src.data_loader import ...`, so the pipeline should too.
  Done on `fix/src-defects`.
- `README.md` / `docs/EXPERIMENTS.md`: when the leap-year fix lands, the model numbers must be
  regenerated and the change logged as an experiment. Logged as E-009; the README is not
  touched on this branch (its Part 2 is being rewritten per the panel report).
- `.gitignore`: `/outputs/` and the root PNGs are already ignored; no change needed for the tests.
  The two root PNG rules are now dead (nothing writes there) and can go with the next
  `.gitignore` change.
