# Test suite and CI: summary

Author: tests agent (wave 1). Files written: `tests/conftest.py`, `tests/test_data_loader.py`,
`tests/test_features.py`, `tests/test_train_model.py`, `tests/test_build_cache.py`,
`tests/test_reproduce_helpers.py`, `.github/workflows/ci.yml`, `pytest.ini`, this file.
No file under `src/`, `scripts/`, `run_pipeline.py` or the requirements files was changed.

Result: `.venv/bin/python -m pytest -q` gives 66 passed, 1 xfailed, 0 warnings in about 6.5 s
(pandas 3.0.6, numpy 2.5.3, scikit-learn 1.9.1, pyarrow 25.0.1, Python 3.12.3). The same
result was obtained from a clean `uv venv` holding exactly what CI installs
(`requirements.txt` + pytest pyarrow ruff), and with `WILDFIRE_DB_PATH` deliberately pointed
at a missing file from a foreign working directory, so nothing in the suite depends on
`data/` or on the caller's environment.

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
| `test_data_loader.py` | 9 | filter is exactly `FIRE_YEAR >= 2010 AND CONT_DATE IS NOT NULL`; the 8 selected columns; dates arrive as text; `WILDFIRE_DB_PATH` is honoured; an explicit path overrides the env var; missing file, env var to a missing file, and non-database file all end in `SystemExit(1)` (defect, see below) |
| `test_features.py` | 17 (1 xfail) | DURATION_DAYS = CONT - DISCOVERY in whole days (hand-built rows and every synthetic row, including the 400-day tail); negative rows dropped with exactly one WARNING on logger `src.features`, no warning otherwise; SIN/COS in [-1, 1] and on the unit circle; day 1 vs day 365 one day apart, day 1 vs day 183 nearly opposite; DOY 366 collides with DOY 1 (known issue, pinned) plus an `xfail(strict=False)` for the intended behaviour; all 13 `CAUSE_*` columns, one-hot exactly one per row; X is exactly the 17 columns in `outputs/reproduction_model.json`; X excludes FIRE_YEAR, FIRE_SIZE_CLASS, both dates, DOY, the target and the raw cause; no NaNs; y shares X's index and keeps original labels; the input frame is not mutated; schema drift when a cause is absent (defect, pinned) |
| `test_train_model.py` | 7 | `split_data` deterministic, 80/20, disjoint, equal to `train_test_split(..., random_state=42)`; `build_model` is 100 trees, depth 10, random_state 42, n_jobs default -1 and override to 1; `train_model` end to end with every sklearn call forced to `n_jobs=1` inside a `tmp_path` CWD, returning a fitted 100-tree forest with the right `feature_names_in_`, non-negative finite predictions, and both PNGs written to the CWD; two runs give identical predictions |
| `test_build_cache.py` | 11 | `build(db_path, cache_path)` writes all 300 rows with the derived columns; dtypes (datetime64, category with the 13 causes, Int8 month); exact DURATION_DAYS / DURATION_HOURS / DISCOVERY_DATETIME for the known rows; DURATION_DAYS matches ground truth for every row including NaN where CONT_DATE is NULL; NaT and NaN hours when a time is NULL or invalid (`2560`) while the day-level duration survives; the negative row is kept (the cache does not filter); `db_sha256` metadata equals the file hash; second call is a no-op ("is up to date", mtime and size unchanged); a stale hash triggers a rebuild; `parse_datetime` directly |
| `test_reproduce_helpers.py` | 23 | `to_datetime` with and without times (valid, whitespace, NULL, empty, hour 24/25, minute 60, 3 and 5 digit strings, letters, missing date), index preserved; `metrics` rmse/mae on known errors, zero on perfect prediction, sign symmetric, "predict 0" MAE equals the target mean; `pct_better` sign convention including the README's 7.05 comparison; `region_of` for all four regions plus Other and NULL, index preserved; the region lists are disjoint, exclude AK, and have 11/14/9 members |

Not covered, on purpose: `run_pipeline.py` (it only chains the three functions and would
need the real database), `scripts/download_data.py` (network), and the Part 1/2 bodies of
`scripts/reproduce.py` (`run_model`, `run_sample_checks`, `run_descriptive` need the real
data and several minutes). The helpers those bodies rely on are covered.

## Defects the tests document (they pass against current behaviour by design)

Each of these is pinned by a test whose name ends in `_DEFECT` or `_KNOWN_ISSUE`, with a
comment at the assertion. When the fix lands, flip the test to the new behaviour in the same
commit.

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

These are proposals only; per the wave-1 rules I did not edit `src/`.

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
- `README.md` / `docs/EXPERIMENTS.md`: when the leap-year fix lands, the model numbers must be
  regenerated and the change logged as an experiment.
- `.gitignore`: `/outputs/` and the root PNGs are already ignored; no change needed for the tests.
