"""
Regenerate every number the README states, plus the baselines and data checks
needed to judge them.

Usage:
    python scripts/reproduce.py                  # everything
    python scripts/reproduce.py --part model     # Part 2 model, baselines, target checks
    python scripts/reproduce.py --part descriptive
    python scripts/reproduce.py --skip-cv        # skip the 5-fold CV (saves a few minutes)

Writes outputs/reproduction.json and figures to outputs/ (or --out).
Checks the database against data.sha256 first and warns on a mismatch.
"""
import argparse
import hashlib
import json
import logging
import os
import sqlite3
import sys
import time

import numpy as np
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.data_loader import DEFAULT_DB_PATH, load_data  # noqa: E402
from src.features import preprocess_data  # noqa: E402
from src.train_model import RANDOM_STATE, build_model, split_data  # noqa: E402

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger('reproduce')

NORTHEAST = ['CT', 'ME', 'MA', 'NH', 'RI', 'VT', 'NY', 'NJ', 'PA']
WEST = ['AZ', 'CA', 'CO', 'ID', 'MT', 'NV', 'NM', 'OR', 'UT', 'WA', 'WY']
SOUTH = ['AL', 'AR', 'FL', 'GA', 'KY', 'LA', 'MS', 'NC', 'OK', 'SC', 'TN', 'TX', 'VA', 'WV']


def region_of(state: pd.Series) -> pd.Series:
    out = pd.Series('Other', index=state.index)
    out[state.isin(WEST)] = 'West'
    out[state.isin(SOUTH)] = 'South'
    out[state.isin(NORTHEAST)] = 'Northeast'
    out[state == 'AK'] = 'Alaska'
    return out


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def check_hash(db_path: str) -> dict:
    expected = open(os.path.join(REPO_ROOT, 'data.sha256')).read().split()[0]
    actual = sha256(db_path)
    if actual != expected:
        logger.warning(f'Database hash {actual} does not match data.sha256 ({expected}). '
                       'Results may not match the recorded ones.')
    else:
        logger.info('Database hash matches data.sha256.')
    return {'expected': expected, 'actual': actual, 'match': actual == expected}


def to_datetime(date: pd.Series, time_str: pd.Series = None) -> pd.Series:
    d = pd.to_datetime(date, format='%m/%d/%Y', errors='coerce')
    if time_str is None:
        return d
    t = time_str.fillna('').astype(str).str.strip()
    ok = t.str.fullmatch(r'\d{4}')
    hh = pd.to_numeric(t.str[:2].where(ok), errors='coerce')
    mm = pd.to_numeric(t.str[2:].where(ok), errors='coerce')
    ok = ok & (hh < 24) & (mm < 60)
    return (d + pd.to_timedelta(hh, unit='h') + pd.to_timedelta(mm, unit='m')).where(ok)


def metrics(y_true, y_pred) -> dict:
    err = np.asarray(y_pred, dtype=float) - np.asarray(y_true, dtype=float)
    return {'rmse': float(np.sqrt(np.mean(err ** 2))), 'mae': float(np.mean(np.abs(err)))}


def pct_better(model: float, base: float) -> float:
    return float(100 * (base - model) / base)


# --------------------------------------------------------------------------- Part 2

def run_model(out_dir: str, skip_cv: bool) -> dict:
    from sklearn.inspection import permutation_importance
    from sklearn.model_selection import KFold, cross_val_score

    res = {}
    df = load_data()
    res['n_loaded'] = int(len(df))
    raw_dur = (pd.to_datetime(df['CONT_DATE'], format='%m/%d/%Y')
               - pd.to_datetime(df['DISCOVERY_DATE'], format='%m/%d/%Y')).dt.days
    res['n_negative_duration'] = int((raw_dur < 0).sum())

    X, y = preprocess_data(df)
    res['n_model'] = int(len(y))
    res['n_features'] = int(X.shape[1])
    res['features'] = list(X.columns)

    q = [0.5, 0.75, 0.9, 0.95, 0.99, 0.999]
    res['target'] = {
        'mean': float(y.mean()), 'std_ddof0': float(y.std(ddof=0)), 'std_ddof1': float(y.std(ddof=1)),
        'median': float(y.median()), 'max': int(y.max()),
        'share_0_days': float((y == 0).mean()), 'share_le_1_day': float((y <= 1).mean()),
        'share_ge_7_days': float((y >= 7).mean()), 'share_ge_30_days': float((y >= 30).mean()),
        'n_gt_365_days': int((y > 365).sum()),
        'percentiles': {str(p): float(y.quantile(p)) for p in q},
    }

    X_train, X_test, y_train, y_test = split_data(X, y)
    res['n_train'], res['n_test'] = int(len(y_train)), int(len(y_test))
    res['std_test_ddof0'] = float(y_test.std(ddof=0))

    if not skip_cv:
        t0 = time.time()
        kf = KFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
        cv = cross_val_score(build_model(), X_train, y_train, cv=kf,
                             scoring='neg_root_mean_squared_error', n_jobs=-1)
        res['cv_rmse_mean'], res['cv_rmse_std'] = float(-cv.mean()), float(cv.std())
        res['cv_rmse_folds'] = [float(-s) for s in cv]
        logger.info(f'CV RMSE {-cv.mean():.4f} (+/- {cv.std():.4f}) in {time.time() - t0:.0f}s')

    rf = build_model()
    rf.fit(X_train, y_train)
    pred = rf.predict(X_test)
    res['model_test'] = metrics(y_test, pred)
    logger.info(f"Test {res['model_test']}")

    # Baselines, fitted on the training rows only, scored on the same test rows.
    cause_cols = [c for c in X.columns if c.startswith('CAUSE_')]
    cause_train = X_train[cause_cols].idxmax(axis=1)
    cause_test = X_test[cause_cols].idxmax(axis=1)
    per_cause_median = y_train.groupby(cause_train).median()
    per_cause_mean = y_train.groupby(cause_train).mean()
    baselines = {
        'predict_mean': np.full(len(y_test), y_train.mean()),
        'predict_median': np.full(len(y_test), y_train.median()),
        'predict_zero': np.zeros(len(y_test)),
        'per_cause_median': cause_test.map(per_cause_median).to_numpy(),
        'per_cause_mean': cause_test.map(per_cause_mean).to_numpy(),
    }
    res['baselines_test'] = {}
    for name, p in baselines.items():
        m = metrics(y_test, p)
        m['model_rmse_pct_better'] = pct_better(res['model_test']['rmse'], m['rmse'])
        m['model_mae_pct_better'] = pct_better(res['model_test']['mae'], m['mae'])
        res['baselines_test'][name] = m
    res['readme_6pct_check'] = {
        'test_rmse_vs_7.05': pct_better(res['model_test']['rmse'], 7.05),
        'test_rmse_vs_full_std': pct_better(res['model_test']['rmse'], res['target']['std_ddof0']),
        'test_rmse_vs_test_std': pct_better(res['model_test']['rmse'], res['std_test_ddof0']),
    }

    # Where the error lives: by true-duration bucket.
    buckets = pd.cut(y_test, [-1, 0, 1, 6, 29, 99, 10_000], labels=['0', '1', '2-6', '7-29', '30-99', '100+'])
    by_bucket = {}
    for b in buckets.cat.categories:
        m = (buckets == b).to_numpy()
        by_bucket[str(b)] = {
            'n': int(m.sum()),
            'model_mean_pred': float(pred[m].mean()) if m.any() else None,
            'model_mae': float(np.abs(pred[m] - y_test.to_numpy()[m]).mean()) if m.any() else None,
            'zero_mae': float(y_test.to_numpy()[m].mean()) if m.any() else None,
            'share_sq_error': float(((pred[m] - y_test.to_numpy()[m]) ** 2).sum()
                                    / ((pred - y_test.to_numpy()) ** 2).sum()),
        }
    res['error_by_true_duration'] = by_bucket

    mdi = pd.Series(rf.feature_importances_, index=X.columns).sort_values(ascending=False)
    res['mdi_importance_top10'] = {k: float(v) for k, v in mdi.head(10).items()}
    rng = np.random.RandomState(RANDOM_STATE)
    idx = rng.choice(len(X_test), size=min(50_000, len(X_test)), replace=False)
    pi = permutation_importance(rf, X_test.iloc[idx], y_test.iloc[idx], n_repeats=5,
                                random_state=RANDOM_STATE, scoring='neg_mean_absolute_error', n_jobs=4)
    perm = pd.Series(pi.importances_mean, index=X.columns).sort_values(ascending=False)
    res['permutation_importance_mae_top10'] = {k: float(v) for k, v in perm.head(10).items()}

    plot_model(rf, X.columns, y_test, pred, out_dir)
    return res


def plot_model(rf, cols, y_test, pred, out_dir):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fi = pd.Series(rf.feature_importances_, index=cols).sort_values().tail(10)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(fi.index, fi.values, color='#4c72b0')
    ax.set_xlabel('Importance (mean decrease in impurity)')
    ax.set_title('Top 10 feature importances (MDI), reproduced')
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, 'feature_importance.png'), dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(y_test, pred, s=2, alpha=0.1)
    m = max(y_test.max(), pred.max())
    ax.plot([0, m], [0, m], 'r--', lw=1, label='Perfect prediction')
    ax.set_xlabel('Actual duration (days)')
    ax.set_ylabel('Predicted duration (days)')
    ax.set_title('Predicted vs. actual duration (test set), reproduced')
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, 'residuals.png'), dpi=120)
    plt.close(fig)


# --------------------------------------------------------------------------- target / sample checks

def run_sample_checks(conn) -> dict:
    res = {}
    df = pd.read_sql_query("""
        SELECT FIRE_YEAR, DISCOVERY_DATE, DISCOVERY_TIME, CONT_DATE, CONT_TIME, FIRE_SIZE,
               FIRE_SIZE_CLASS, NWCG_CAUSE_CLASSIFICATION, NWCG_REPORTING_AGENCY,
               SOURCE_SYSTEM_TYPE, OWNER_DESCR, STATE
        FROM Fires WHERE FIRE_YEAR >= 2010""", conn)
    has = df['CONT_DATE'].notna()
    res['n_2010_plus'] = int(len(df))
    res['n_2010_plus_missing_cont_date'] = int((~has).sum())
    res['share_2010_plus_missing_cont_date'] = float((~has).mean())

    def shares(col):
        t = pd.crosstab(df[col].fillna('NA'), has.map({True: 'kept', False: 'dropped'}), normalize='columns')
        return {k: {c: float(v) for c, v in row.items()} for k, row in t.iterrows()}

    res['kept_vs_dropped'] = {c: shares(c) for c in
                              ['FIRE_SIZE_CLASS', 'NWCG_CAUSE_CLASSIFICATION', 'NWCG_REPORTING_AGENCY',
                               'SOURCE_SYSTEM_TYPE']}
    res['kept_vs_dropped']['median_fire_size'] = {
        'kept': float(df.loc[has, 'FIRE_SIZE'].median()), 'dropped': float(df.loc[~has, 'FIRE_SIZE'].median())}
    res['kept_vs_dropped']['region'] = shares_series(region_of(df['STATE']), has)
    miss_by_state = (~has).groupby(df['STATE']).mean().sort_values(ascending=False)
    res['missing_cont_share_by_state_top10'] = {k: float(v) for k, v in miss_by_state.head(10).items()}
    res['missing_cont_share_by_year'] = {int(k): float(v) for k, v in (~has).groupby(df['FIRE_YEAR']).mean().items()}

    # Hour-level duration where both times exist.
    k = df[has].copy()
    k['disc'] = to_datetime(k['DISCOVERY_DATE'], k['DISCOVERY_TIME'])
    k['cont'] = to_datetime(k['CONT_DATE'], k['CONT_TIME'])
    k['days'] = (pd.to_datetime(k['CONT_DATE'], format='%m/%d/%Y')
                 - pd.to_datetime(k['DISCOVERY_DATE'], format='%m/%d/%Y')).dt.days
    k['hours'] = (k['cont'] - k['disc']).dt.total_seconds() / 3600
    both = k['hours'].notna()
    res['hours'] = {
        'n_with_both_times': int(both.sum()), 'share_with_both_times': float(both.mean()),
        'n_negative_hours': int((k['hours'] < 0).sum()),
    }
    for d in [0, 1, 2]:
        h = k.loc[both & (k['days'] == d), 'hours']
        res['hours'][f'day{d}_hours_percentiles'] = {str(p): float(h.quantile(p)) for p in [0.1, 0.5, 0.9, 0.99]}
    h1 = k.loc[both & (k['days'] == 1), 'hours']
    res['hours']['share_1day_fires_under_12h'] = float((h1 < 12).mean())
    return res


def shares_series(s: pd.Series, has: pd.Series) -> dict:
    t = pd.crosstab(s, has.map({True: 'kept', False: 'dropped'}), normalize='columns')
    return {k: {c: float(v) for c, v in row.items()} for k, row in t.iterrows()}


# --------------------------------------------------------------------------- Part 1

def run_descriptive(conn, out_dir: str) -> dict:
    from scipy import stats

    res = {}
    df = pd.read_sql_query("""
        SELECT FIRE_YEAR, DISCOVERY_DATE, DISCOVERY_DOY, DISCOVERY_TIME, CONT_DATE, CONT_TIME,
               NWCG_CAUSE_CLASSIFICATION, NWCG_GENERAL_CAUSE, FIRE_SIZE, FIRE_SIZE_CLASS,
               OWNER_DESCR, STATE, FIRE_NAME
        FROM Fires""", conn)
    res['n_rows'] = int(len(df))
    res['n_columns_table'] = len(conn.execute('PRAGMA table_info(Fires)').fetchall())

    def blank(s):
        return s.isna() | (s.astype(str).str.strip() == '')

    res['missing_cont_date'] = int(blank(df['CONT_DATE']).sum())
    res['missing_discovery_time'] = int(blank(df['DISCOVERY_TIME']).sum())
    res['missing_cont_time'] = int(blank(df['CONT_TIME']).sum())

    i = df['FIRE_SIZE'].idxmax()
    res['largest_fire'] = {'acres': float(df.at[i, 'FIRE_SIZE']), 'name': df.at[i, 'FIRE_NAME'],
                           'year': int(df.at[i, 'FIRE_YEAR']), 'state': df.at[i, 'STATE']}
    res['min_fire_size'] = float(df['FIRE_SIZE'].min())

    by_class = df.groupby('NWCG_CAUSE_CLASSIFICATION')['FIRE_SIZE'].agg(['count', 'sum'])
    res['by_cause_classification'] = {k: {'fires': int(r['count']), 'acres': float(r['sum']),
                                          'share_fires': float(r['count'] / len(df)),
                                          'share_acres': float(r['sum'] / df['FIRE_SIZE'].sum())}
                                      for k, r in by_class.iterrows()}
    res['total_acres'] = float(df['FIRE_SIZE'].sum())
    res['top_general_cause_by_class_BC'] = {
        c: df.loc[df['FIRE_SIZE_CLASS'] == c, 'NWCG_GENERAL_CAUSE'].value_counts(normalize=True).head(3).to_dict()
        for c in ['B', 'C']}

    owner = df.groupby('OWNER_DESCR')['FIRE_SIZE'].sum().sort_values(ascending=False)
    res['acres_by_owner_top6'] = {k: float(v) for k, v in owner.head(6).items()}

    # Class G trend.
    g = df[df['FIRE_SIZE_CLASS'] == 'G']
    gy = g.groupby('FIRE_YEAR')['FIRE_SIZE'].sum().reindex(range(1992, 2021), fill_value=0)
    lr = stats.linregress(gy.index, gy.values)
    tau = stats.kendalltau(gy.index, gy.values)
    ts = stats.theilslopes(gy.values, gy.index)
    res['class_g_trend'] = {
        'acres_by_year': {int(k): float(v) for k, v in gy.items()},
        'ols_slope_acres_per_year': float(lr.slope), 'ols_p': float(lr.pvalue),
        'kendall_tau': float(tau.statistic), 'kendall_p': float(tau.pvalue),
        'theil_sen_slope': float(ts.slope),
        'first_half_mean_1992_2005': float(gy.loc[1992:2005].mean()),
        'second_half_mean_2006_2020': float(gy.loc[2006:2020].mean()),
    }
    ny = df.groupby('FIRE_YEAR').size()
    tau_n = stats.kendalltau(ny.index, ny.values)
    res['fire_count_trend'] = {'kendall_tau': float(tau_n.statistic), 'kendall_p': float(tau_n.pvalue),
                               'count_by_year': {int(k): int(v) for k, v in ny.items()}}

    month = pd.to_datetime(df['DISCOVERY_DATE'], format='%m/%d/%Y').dt.month
    df['MONTH'] = month
    df['REGION'] = region_of(df['STATE'])

    # Arkansas June Class G.
    ar = df[(df['STATE'] == 'AR') & (df['FIRE_SIZE_CLASS'] == 'G')]
    res['arkansas_class_g'] = {
        'acres_by_month': {int(k): float(v) for k, v in ar.groupby('MONTH')['FIRE_SIZE'].sum().items()},
        'n_by_month': {int(k): int(v) for k, v in ar.groupby('MONTH').size().items()},
        'june_fires': ar[ar['MONTH'] == 6][['FIRE_YEAR', 'FIRE_NAME', 'FIRE_SIZE', 'OWNER_DESCR',
                                            'NWCG_GENERAL_CAUSE']].sort_values('FIRE_SIZE', ascending=False)
        .head(10).to_dict('records'),
    }

    # Texas December.
    tx = df[df['STATE'] == 'TX']
    res['texas'] = {
        'n_by_month': {int(k): int(v) for k, v in tx.groupby('MONTH').size().items()},
        'acres_by_month': {int(k): float(v) for k, v in tx.groupby('MONTH')['FIRE_SIZE'].sum().items()},
        'class_g_n_by_month': {int(k): int(v) for k, v in
                               tx[tx['FIRE_SIZE_CLASS'] == 'G'].groupby('MONTH').size().items()},
        'december_top_years_acres': {int(k): float(v) for k, v in
                                     tx[tx['MONTH'] == 12].groupby('FIRE_YEAR')['FIRE_SIZE'].sum()
                                     .sort_values(ascending=False).head(5).items()},
    }

    # Northeast by year.
    ne = df[df['REGION'] == 'Northeast']
    ne_n = ne.groupby('FIRE_YEAR').size()
    ne_a = ne.groupby('FIRE_YEAR')['FIRE_SIZE'].sum()
    res['northeast'] = {
        'states': NORTHEAST,
        'n_by_year': {int(k): int(v) for k, v in ne_n.items()},
        'acres_by_year': {int(k): float(v) for k, v in ne_a.items()},
        'z_2010_count': float((ne_n.get(2010, 0) - ne_n.mean()) / ne_n.std()),
        'z_2010_acres': float((ne_a.get(2010, 0) - ne_a.mean()) / ne_a.std()),
        'n_2010_by_state': {k: int(v) for k, v in ne[ne['FIRE_YEAR'] == 2010].groupby('STATE').size().items()},
        'n_by_state_year': ne.groupby(['STATE', 'FIRE_YEAR']).size().unstack(fill_value=0)
        .loc[:, 2006:2014].to_dict('index'),
    }

    # Seasonal geography of large fires.
    g = df[df['FIRE_SIZE_CLASS'] == 'G']
    res['class_g_region_by_month'] = pd.crosstab(g['MONTH'], g['REGION']).to_dict('index')

    # Duration by region and month (day-level, all years with a containment date).
    dur = (pd.to_datetime(df['CONT_DATE'], format='%m/%d/%Y', errors='coerce')
           - pd.to_datetime(df['DISCOVERY_DATE'], format='%m/%d/%Y')).dt.days
    df['DUR'] = dur
    ok = dur.notna() & (dur >= 0)
    res['mean_duration_by_region'] = {k: float(v) for k, v in df[ok].groupby('REGION')['DUR'].mean().items()}
    west = df[ok & (df['REGION'] == 'West')]
    res['west_mean_duration_by_month'] = {int(k): float(v) for k, v in west.groupby('MONTH')['DUR'].mean().items()}

    # Control Efficiency Score: 1 / mean(acres per hour to containment), by owner.
    disc = to_datetime(df['DISCOVERY_DATE'], df['DISCOVERY_TIME'])
    cont = to_datetime(df['CONT_DATE'], df['CONT_TIME'])
    hours = (cont - disc).dt.total_seconds() / 3600
    c = df.assign(HOURS=hours)
    c = c[c['HOURS'] > 0]
    c['APH'] = c['FIRE_SIZE'] / c['HOURS']
    ces = c.groupby('OWNER_DESCR')['APH'].agg(['count', 'mean', 'median'])
    ces['ces_mean_based'] = 1 / ces['mean']
    ces['ces_median_based'] = 1 / ces['median']
    ces = ces.sort_values('count', ascending=False).head(12)
    res['control_efficiency'] = {
        'n_fires_with_positive_hours': int(len(c)),
        'by_owner': {k: {kk: float(vv) for kk, vv in r.items()} for k, r in ces.iterrows()},
        'rank_by_mean_based': list(ces['ces_mean_based'].sort_values(ascending=False).index),
        'rank_by_median_based': list(ces['ces_median_based'].sort_values(ascending=False).index),
    }
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--part', choices=['model', 'descriptive', 'all'], default='all')
    ap.add_argument('--out', default=os.path.join(REPO_ROOT, 'outputs'))
    ap.add_argument('--skip-cv', action='store_true')
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    db_path = os.environ.get('WILDFIRE_DB_PATH', DEFAULT_DB_PATH)
    import sklearn
    result = {'data_hash': check_hash(db_path),
              'env': {'python': sys.version.split()[0], 'pandas': pd.__version__,
                      'numpy': np.__version__, 'scikit-learn': sklearn.__version__}}
    if args.part in ('model', 'all'):
        result['model'] = run_model(args.out, args.skip_cv)
    conn = sqlite3.connect(db_path)
    try:
        if args.part in ('model', 'all'):
            result['sample'] = run_sample_checks(conn)
        if args.part in ('descriptive', 'all'):
            result['descriptive'] = run_descriptive(conn, args.out)
    finally:
        conn.close()

    path = os.path.join(args.out, f'reproduction_{args.part}.json')
    with open(path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    logger.info(f'Wrote {path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
