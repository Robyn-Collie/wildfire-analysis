"""
Download the USFS wildfire occurrence database into data/.

Source: Short, Karen C. 2022. Spatial wildfire occurrence data for the United States,
1992-2020 [FPA_FOD_20221014]. 6th Edition. Fort Collins, CO: Forest Service Research
Data Archive. https://doi.org/10.2737/RDS-2013-0009.6

The SQLite archive is about 214 MB zipped and about 960 MB unzipped.
If the automatic download fails, the script prints manual steps instead.
"""
import os
import shutil
import sys
import urllib.request
import zipfile

CATALOG_URL = 'https://www.fs.usda.gov/rds/archive/catalog/RDS-2013-0009.6'
ZIP_URL = ('https://www.fs.usda.gov/rds/archive/products/RDS-2013-0009.6/'
           'RDS-2013-0009.6_Data_Format4_SQLITE.zip')
DB_FILENAME = 'FPA_FOD_20221014.sqlite'

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, 'data')
ZIP_PATH = os.path.join(DATA_DIR, 'RDS-2013-0009.6_Data_Format4_SQLITE.zip')
DB_PATH = os.path.join(DATA_DIR, DB_FILENAME)


def manual_instructions() -> None:
    print()
    print('Manual download:')
    print(f'  1. Open {CATALOG_URL}')
    print('  2. Download "RDS-2013-0009.6_Data_Format4_SQLITE.zip" (about 214 MB).')
    print(f'  3. Unzip it and move {DB_FILENAME} into the data/ folder of this repo.')
    print('     (Or set the WILDFIRE_DB_PATH environment variable to wherever you put it.)')


def report(block_num: int, block_size: int, total_size: int) -> None:
    if total_size > 0:
        pct = min(100, block_num * block_size * 100 // total_size)
        print(f'\r  {pct:3d}%', end='', flush=True)


def main() -> int:
    if os.path.exists(DB_PATH):
        print(f'{DB_FILENAME} is already in data/. Nothing to do.')
        return 0

    os.makedirs(DATA_DIR, exist_ok=True)

    try:
        if not os.path.exists(ZIP_PATH):
            print(f'Downloading {ZIP_URL}')
            urllib.request.urlretrieve(ZIP_URL, ZIP_PATH, reporthook=report)
            print()

        print('Extracting the SQLite database...')
        with zipfile.ZipFile(ZIP_PATH) as zf:
            members = [m for m in zf.namelist() if m.lower().endswith('.sqlite')]
            if not members:
                raise RuntimeError('No .sqlite file found inside the archive.')
            with zf.open(members[0]) as src, open(DB_PATH, 'wb') as dst:
                shutil.copyfileobj(src, dst)
    except Exception as e:
        print(f'\nAutomatic download failed: {e}')
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        manual_instructions()
        return 1

    os.remove(ZIP_PATH)
    print(f'Done: {os.path.relpath(DB_PATH, REPO_ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
