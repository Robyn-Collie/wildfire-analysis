# Data version

All results in this repo come from this exact file. `scripts/reproduce.py` checks the hash before it runs.

| Field | Value |
|---|---|
| Dataset | Short, Karen C. 2022. *Spatial wildfire occurrence data for the United States, 1992–2020 [FPA_FOD_20221014].* 6th Edition. Forest Service Research Data Archive. |
| DOI | https://doi.org/10.2737/RDS-2013-0009.6 |
| Download URL | https://www.fs.usda.gov/rds/archive/products/RDS-2013-0009.6/RDS-2013-0009.6_Data_Format4_SQLITE.zip |
| File | `data/FPA_FOD_20221014.sqlite` (958,480,384 bytes) |
| SHA-256 | `04f5ab8bff6880a8ee76b4a825a66b5f4db0b800dc5971a919cb743251a965a8` (also in `data.sha256`) |
| Downloaded | 2026-09-25 |
| Table `Fires` | 2,303,566 rows × 39 columns (37 attribute fields plus `OBJECTID` and the `Shape` geometry) |

To check your copy: `sha256sum -c data.sha256` (Linux/macOS/Git Bash) or `Get-FileHash data/FPA_FOD_20221014.sqlite` (PowerShell).
