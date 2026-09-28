# External datasets joined to the FPA FOD

Every file here is fetched by `scripts/download_external.py` into `data/external/<name>/` and hash-checked
(`python scripts/download_external.py --verify`). `data/external/` is not committed. The FPA FOD itself is
documented in `docs/DATA_VERSION.md`; the download script never touches `data/FPA_FOD_20221014.sqlite` or
`data/fires.parquet`. Hashes are SHA-256 of the archive as downloaded. Dates are the download date.

| Name | Dataset and citation | URL used (resolved from the API at run time) | License | Size | SHA-256 | Date | Join key | Coverage in FPA FOD |
|---|---|---|---|---|---|---|---|---|
| `ics209plus` | ICS-209-PLUS 2.0, wildfire tables 1999-2020. St. Denis, L. A., Short, K. C., McConnell, K., Cook, M. C., Mietkiewicz, N. P., Buckland, M., Balch, J. K. (2023). *All-hazards dataset mined from the US National Incident Management System 1999-2020.* figshare, v3, 2023-01-10, https://doi.org/10.6084/m9.figshare.19858927.v3 | `https://ndownloader.figshare.com/files/38766504` (file `ics209plus-wildfire.zip` on https://api.figshare.com/v2/articles/19858927) | CC BY 4.0 | 48,717,736 bytes | `a17c08ede2824e9002fcda112301793c9e59ce1f7ed7eb1e16a762be85ade30f` | 2026-09-25 | FPA FOD `ICS_209_PLUS_INCIDENT_JOIN_ID` = ICS-209-PLUS `INCIDENT_ID` in `ics209-plus-wf_incidents_1999to2020.csv` | 33,494 FPA FOD rows carry the key, 33,476 match (29,921 distinct incidents of 34,622 in the table). 2010-2020 fires >= 300 acres: 79.5% matched (class D 33.7%, E 71.1%, F 84.6%, G 95.5%). Classes A-C under 1.5%. |
| `padus_conus` | PAD-US 4.1 Raster Analysis, CONUS, which also contains the Vector Analysis file geodatabase `PADUS4_1VectorAnalysis_CONUS.gdb`. U.S. Geological Survey (USGS) Gap Analysis Project (GAP), 2024, *Protected Areas Database of the United States (PAD-US) 4.1*: U.S. Geological Survey data release, https://doi.org/10.5066/P96WBCHS. Child item "PAD-US 4.1 Raster Analysis": https://www.sciencebase.gov/catalog/item/6759b67ed34edfeb8710a3db | `https://www.sciencebase.gov/catalog/file/get/6759b67ed34edfeb8710a3db?f=__disk__c6%2F3a%2Fce%2Fc63aceb8653358a6d0438b141d86bc6fe4b51429` (`PADUS4_1_Raster_CONUS.zip`; only the `.gdb` and the report/stats text files are extracted, the 10 GB raster is not) | USGS data release, public domain; "USGS provides no legal warranty for the use of this data" (metadata) | 744,032,421 bytes | `c830855c92f8599dc63413ddbd3044eb7bf3d92dd14a909779e6adcba2d0ba57` | 2026-09-25 | Point in polygon: ignition `LATITUDE`/`LONGITUDE` (EPSG:4326) projected to the layer CRS (USA Contiguous Albers Equal Area Conic USGS version) and joined with `geopandas.sjoin(predicate='within')`, 250k points per chunk | 2,256,199 CONUS points submitted, 2,256,174 fall in a polygon (25 do not: coordinates offshore or in the wrong state). 322,263 polygons. |
| `padus_ak` | Same release, Alaska: `PADUS4_1_Raster_AK.zip` containing `PADUS4_1VectorAnalysis_AK.gdb` | `https://www.sciencebase.gov/catalog/file/get/6759b67ed34edfeb8710a3db?f=__disk__04%2F4a%2Fd3%2F044ad35d33f654ade579925b22f4c95af21d904d` | as above | 151,544,095 bytes | `d943e74b36238f973156d06c3e1a6e53896f9bde401535e36d68ec95da0cc618` | 2026-09-25 | as above, layer CRS (Alaska Albers) | 15,195 AK points, all matched. 1,451 polygons. |
| `padus_hi` | Same release, Hawaii: `PADUS4_1_Raster_HI.zip` containing `PADUS4_1VectorAnalysis_HI.gdb` | `https://www.sciencebase.gov/catalog/file/get/6759b67ed34edfeb8710a3db?f=__disk__b6%2Fb1%2Ff9%2Fb6b1f98d0cf5990ebdd323986e11c0065ea0fcd5` | as above | 14,122,874 bytes | `af99b44bcfbace0a7d763740a7da40bb9a1b2dae4b6f2bec7324cefae8f024f0` | 2026-09-25 | as above, layer CRS (Hawaii Albers) | 9,970 HI points, all matched. 1,019 polygons. |
| `padus_national_gdb` | PAD-US 4.1 full inventory geodatabase `PADUS4_1Geodatabase.zip` (1,523,434,496 bytes), parent item https://www.sciencebase.gov/catalog/item/652d4fc5d34e44db0e2ee45e | not downloadable by script (see below) | as above | 1,523.4 MB | not downloaded | | would have been the same point-in-polygon join on the `PADUS4_1Combined_Proclamation_Marine_Fee_Designation_Easement` feature class | not used |

## Why the Vector Analysis file and not the national geodatabase

The national geodatabase and the PAD-US 4.1 state downloads (ScienceBase item 6759abcfd34edfeb8710a004) are
stored on S3 and served only through the ScienceBase File Manager, a JavaScript app that calls
`https://api.sciencebase.gov/graphql` (`getS3DownloadUrl`) with a Keycloak bearer token; without a login the
endpoint answers `UNAUTHENTICATED`, and the alternative `requestDownload` page is a captcha form. The catalog
item JSON lists these files with `"pathOnDisk": "__s3__"`. Files with a `__disk__` path (the Raster Analysis
zips) are served directly by `catalog/file/get`, and those zips contain the PAD-US 4.1 **Vector Analysis file**.

The Vector Analysis file is, per its FGDC metadata (fetched from
`https://www.sciencebase.gov/catalog/file/get/6759b69fd34edfeb8710a3ea?f=__disk__60%2Fc9%2F95%2F60c995a68e09ecd9f6757858886b7f0f324e953e`):

> "The PAD-US 4.1 Combined Fee, Designation, Easement feature class (with Military Lands and Tribal Areas from the
> Proclamation and Other Planning Boundaries feature class) was modified to remove overlaps, avoiding overestimation
> in protected area statistics and to support user needs. A Python scripted process associated with this data
> release prioritized overlapping designations (e.g. Wilderness within a National Forest) based upon their relative
> biodiversity conservation status (e.g. GAP Status Code 1 over 2), public access values (in the order of Closed,
> Restricted, Open, Unknown), and geodatabase load order".

So it is the same combined feature class the brief asked for, already flattened by the rule the brief asked us to
apply (lowest GAP status wins), clipped to Census state boundaries and padded with "Non-PAD-US Area" polygons.
Consequences: every ignition point lands in exactly one polygon (`n_overlaps` is 1 for all matched points and the
multiplicity rule in `analysis/conservation.py` never fires); "Non-PAD-US Area" is recorded as GAP status `none`;
Puerto Rico and the other territories are not covered (22,202 PR ignitions are `unmatched`). The field names used
are `Unit_Nm`, `Mang_Type`, `Mang_Name`, `Des_Tp`, `GAP_Sts`, `FeatClass`, `Pub_Access` (and `GAP_Sts_Prity` for
the tie-break). GAP status domain, from the same metadata: 1 "managed for biodiversity - disturbance events proceed
or are mimicked"; 2 "managed for biodiversity - disturbance events suppressed"; 3 "managed for multiple uses -
subject to extractive (e.g. mining or logging) or OHV use"; 4 "no known mandate for biodiversity protection".

## Per-fire join output

`data/external/padus/fires_padus.parquet` (14.5 MB, not committed; rebuilt by
`python -m analysis.conservation --rebuild-padus`): one row per FPA FOD record with `FOD_ID`, `Unit_Nm`,
`Mang_Type`, `Mang_Name`, `Des_Tp`, `GAP_Sts`, `FeatClass`, `Pub_Access`, `n_overlaps`, `extent` (CONUS, AK, HI or
null). Runtime of the full join: about 190 s on 4 CPUs (75 s to read the CONUS layer, 8 s per 250k-point chunk),
peak memory about 4 GB.

## ICS-209-PLUS fields used

From `ics209-plus-wf_incidents_1999to2020.csv` (definitions from `ics209plus-reference.zip`, file
`ics209-plus-wf-incident_field-definitions.csv`, fetched from `https://ndownloader.figshare.com/files/38766492`):
`INCIDENT_ID` (join key, "Unique ID (Year+Inc#+Inc Name)"), `INCIDENT_NAME`, `INCTYP_ABBREVIATION`, `CAUSE`
("Human, Lightning, or Unknown"; coded H/L/U/O), `COMPLEX`, `FINAL_ACRES`, `STR_DESTROYED_TOTAL` and
`STR_DESTROYED_RES_TOTAL` ("zero values included"), `STR_DAMAGED_TOTAL`, `STR_THREATENED_MAX` ("Maximum number of
structures threatened", 38% filled), `WF_PEAK_PERSONNEL` ("Maximum value for TOTAL_PERSONNEL", 79% filled),
`TOTAL_PERSONNEL_SUM`, `PROJECTED_FINAL_IM_COST` ("Estimated final incident management cost", 65% filled),
`EVACUATION_REPORTED` ("2002+ only, 2014+ set to true if PEAK_EVACUATIONS > 0"), `PEAK_EVACUATIONS` (new in 2.0,
5.3% filled), `FATALITIES`, `INJURIES_TOTAL`, `INC_MGMT_NUM_SITREPS`, `START_YEAR`, `POO_STATE`, `FOD_FIRE_NUM`,
`LRGST_FOD_ID` ("FOD Identifier for the largest FOD linked fire").

## Datasets considered and not yet joined

MTBS perimeters and severity, SILVIS WUI, LANDFIRE, NLCD and USFWS critical habitat: see
`docs/review/panel-conservation.md` section (e) for verified landing pages, sizes and effort.

## FPA FOD-Attributes (weather, fuels, terrain, protection, social context)

Pourmohamad, Y., Abatzoglou, J. T., Belval, E. J., Fleishman, E., Short, K., Reeves, M. C., Nauslar, N., Higuera, P. E., Henderson, E., Ball, S., AghaKouchak, A., Prestemon, J. P., Olszewski, J., and Sadegh, M. (2024). Physical, social, and biological attributes for improved understanding and prediction of wildfires: FPA FOD-Attributes dataset. *Earth System Science Data* 16: 3045-3060, https://doi.org/10.5194/essd-16-3045-2024. Data: version 1.0, https://doi.org/10.5281/zenodo.8381129, **CC BY 4.0**. Fetched by `scripts/download_attributes.py` from `https://zenodo.org/api/records/8381129/files/<YYYY>_FPA_FOD_cons.csv/content` on 2026-09-25 into `data/external/fpa_fod_attributes/` and converted to `data/attributes_2010_2020.parquet` (about 80 of 308 columns; every `*_5D_*` column excluded). Join key `FOD_ID`: 100% of fires 2010-2018, 98.3% in 2019 (1,071 fires without an attribute row), 99.9% in 2020 (`outputs/model/attributes_join.csv`). Attributes cover the conterminous US only.

| File | Bytes | SHA-256 |
|---|---|---|
| `2010_FPA_FOD_cons.csv` | 190,672,745 | `c7761457f15f065e4c89ac2bf19eee7bc5ee0cc8c769c9c70c4e7184f7020269` |
| `2011_FPA_FOD_cons.csv` | 222,000,668 | `5d962375785b0addeb69d2a1d50890236b3d8c2f67dc5db1258bacfcf0e1afbd` |
| `2012_FPA_FOD_cons.csv` | 166,891,051 | `7614f896129c8a8103162672a14812112b185d4b617c939d594d27991db6c27d` |
| `2013_FPA_FOD_cons.csv` | 150,155,219 | `0dcf2cd88791aceb91d7fe249f57be55a29579f665228ab720cb8dc77af43fb6` |
| `2014_FPA_FOD_cons.csv` | 160,447,054 | `69dcfdd455a8515475d92ca337ec16a96baccf146721766e9875de954426acf7` |
| `2015_FPA_FOD_cons.csv` | 175,425,318 | `d813563b44ff4055a3e7de31070babd468708619515a43aae82dd89b93aa7b20` |
| `2016_FPA_FOD_cons.csv` | 188,108,189 | `4145c8e8b2ba9a58a9c287ae6e0eb8ec652cc49a5d83a7b352b480a9ac223006` |
| `2017_FPA_FOD_cons.csv` | 188,877,690 | `52f5025f958d9c0e7672d907aebfac2e5addb17256bb4a892bc77e3a0a17848e` |
| `2018_FPA_FOD_cons.csv` | 186,160,898 | `f1267c0e8f3a4d081e36b6e8fced0c5534ad9b2fd6824d5a6fa1a5814c845270` |
| `2019_FPA_FOD_cons.csv` | 143,602,358 | `217c9b808b7a90271090aa2912386969daff22daab0305d9ccfd1fe3e9797372` |
| `2020_FPA_FOD_cons.csv` | 167,785,443 | `79e0cbc27dad54b4ca0af66884f794de21d15223ffe3e2b329bae92c457bdec1` |

## Sources added for version 2 of the site (2026-09-26)

None of these is joined to FPA FOD records. Each is kept as its own series, and the site labels it by source.

### NIFC national annual totals, 1983-2025 (`analysis/nifc.py`)

National Interagency Coordination Center, "Wildfires and Acres", https://www.nifc.gov/fire-information/statistics/wildfires, accessed 2026-09-26. Public domain (U.S. government work).

- Raw HTML: `data/external/nifc/wildfires_2026-09-26.html`, SHA-256 `91d1baa33c1c227624dbcd2d2cad1b4b80ff75e08805c7720f9ed36ad97f5533`.
- Parsed table: `data/external/nifc/nifc_annual.csv` (year, fires, acres; 43 years).
- Cross-check: the first site's cached `national_annual.json` agrees in every year (`nifc.v1_cache_cross_check`).
- Use: national trend only. The site does not use the 1983-1984 fire counts, which are anomalously low (`nifc.count_flag_1983_84`).

### NOAA nClimDiv state climate, 1992-2020 (`analysis/drivers.py`)

NOAA NCEI Climate Divisional Database (nClimDiv), doi:10.7289/V5M32STR, https://www.ncei.noaa.gov/pub/data/cirs/climdiv/, accessed 2026-09-26. Public domain.

| File | SHA-256 |
|---|---|
| `climdiv-pdsist-v1.0.0-20260904` (Palmer Drought Severity Index, state) | `f182d76631c6fa35e637cc4bd6597ffbb07cb14b9f749469527f23b1ccaed802` |
| `climdiv-tmpcst-v1.0.0-20260904` (average temperature, state) | `eba0699e448cb01a531462dbdb81a46015b44ae05d473b4e6124c5a5d6c50d28` |
| `climdiv-pcpnst-v1.0.0-20260904` (precipitation, state) | `56b67e12075a65213d7a2cbaf39ef3ba0cee25dd84f562cd767e27bdcd39c60b` |

- State codes were checked against `state-readme.txt` in the same directory: 50 codes, no mismatches (`drivers.state_code_verification`).
- Join: May-October means per state-year, joined to FPA FOD acres summed by `STATE` and `FIRE_YEAR`, plus the coverage flag from `outputs/coverage_state_year.csv`.

### WFIGS incident locations, 2021-2025 (`analysis/wfigs.py`)

Wildland Fire Interagency Geospatial Services (WFIGS), "WFIGS Incident Locations", layer 0 (full history), https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations/FeatureServer/0, accessed 2026-09-26. Public domain (U.S. government work, NIFC open data).

- Query: `IncidentTypeCategory = 'WF' AND FireDiscoveryDateTime >= TIMESTAMP '2021-01-01 00:00:00' AND FireDiscoveryDateTime < TIMESTAMP '2026-01-01 00:00:00'`, `outSR=4326`, 2,000 rows a page, 98 pages.
- Fields kept: listed in claim `wfigs.query`. The layer schema is in `data/external/wfigs/layer_schema.json`.
- Rows: 195,139 fetched, 195,093 after de-duplicating on `UniqueFireIdentifier`. None was dropped for a missing location or date; 33,328 locations were taken from the point geometry.
- Rows by discovery year: 2021 36,898; 2022 37,807; 2023 37,147; 2024 41,507; 2025 41,734 (`wfigs.rows_per_year`).
- Clean file: `data/external/wfigs/wfigs_2021_2025.parquet`, SHA-256 `158ef4c817fe6b6716103856e32e75b1110b7201842d8b4fcdf02ff05d08d4d1`.
- Size field precedence: `IncidentSize`, then `FinalAcres`, then `DiscoveryAcres`.
- Cause and owner mappings are in `analysis/wfigs.py` and in claim `wfigs.cleaning`.
- Comparability: WFIGS holds about half as many fires a year as FPA FOD 2016-2020, and cause is missing for half of them (`wfigs.comparability_verdict`). It is never spliced onto an FPA FOD series.
