# Data sources for the wildfire-analysis rebuild

## Verification note

Every URL marked "verified" below was fetched successfully on 2026-09-25 (WebFetch, curl, or a public REST API), and every number quoted about a file (size, row count, column count) comes from a download or API response made that day. Publisher HTML pages that returned 403 or a login redirect are noted; for those, the citation was verified through the Crossref API (api.crossref.org) and the abstract through Europe PMC or Semantic Scholar, which count as fetches of the record but not of the publisher page.

Fetches that failed or were only partly readable (treat their details as unverified unless another source is cited):

| URL | Result | What was used instead |
|---|---|---|
| https://fpafod.boisestate.edu/ and /About | HTTP 503 twice via WebFetch; TLS failure via curl | Zenodo record and API (verified) |
| https://spei.csic.es/database.html | WebFetch timed out twice; curl HEAD returned 200 | Not read; gridMET provides SPEI/SPI/PDSI instead (verified) |
| https://wfdss.usgs.gov/ (and /wfdss/WFDSS_Home.shtml) | 404, then connection reset | None; WFDSS marked unverified |
| https://data-nifc.opendata.arcgis.com/ | Page loaded with no content (JavaScript app) | NIFC ArcGIS REST API (verified) |
| https://ecos.fws.gov/ecp/report/table/critical-habitat.html | JavaScript-only page | ScienceBase item and HTTP HEAD on the shapefile zip (verified) |
| https://www.mtbs.gov/direct-download and https://burnseverity.cr.usgs.gov/direct-download | Loaded but content is a redirect stub | https://www.mtbs.gov/ and /faqs and /product-descriptions (verified) |
| https://hazards.fema.gov/nri/data-resources and /nri/ | 301 to a different FEMA tool | OpenFEMA NRI data page (verified) |
| https://www.ncei.noaa.gov/products/vaisala-national-lightning-detection-network | 404 | NCEI lightning products page (verified) |
| https://www.nature.com/articles/... (two articles) | Login redirect | PMC copy or Crossref/Europe PMC API |
| figshare.com HTML pages | 403 | api.figshare.com (verified) |

Repo facts used for join tests come from `data/fires.parquet` (2,303,566 rows; see AGENT_CONTEXT and `docs/review/REPRODUCTION.md`).

Definitions used in this document. "CONUS" means the 48 contiguous states plus DC; in FPA FOD terms, `STATE NOT IN ('AK','HI','PR')`. "Large fire" is not defined here; the modelling brief should define it (see LITERATURE.md, Nagy et al. 2018 for a per-ecoregion top-decile definition versus fixed size classes). Effort estimates: S = under a day with the existing parquet, M = one to three days including a spatial join, L = a week or more, or requires infrastructure the repo does not have. Lens flags: (a) large-fire probability model, (b) conservation lens, (c) descriptive context.

---

## Source 1 (recommended first): FPA FOD-Attributes (Pourmohamad et al. 2024)

**Status: exists as described, verified, and it does most of the join work for this project.** It is not on the USFS Research Data Archive; it is on Zenodo. No RDS-2023-0043 record exists for it (search returned only the Zenodo DOI and the ESSD paper).

| Item | Verified value |
|---|---|
| Paper | Pourmohamad, Y., Abatzoglou, J. T., Belval, E. J., Fleishman, E., Short, K., Reeves, M. C., Nauslar, N., Higuera, P. E., Henderson, E., Ball, S., AghaKouchak, A., Prestemon, J. P., Olszewski, J., and Sadegh, M. (2024). Physical, social, and biological attributes for improved understanding and prediction of wildfires: FPA FOD-Attributes dataset. Earth System Science Data 16(6): 3045-3060. https://doi.org/10.5194/essd-16-3045-2024 (verified; article page https://essd.copernicus.org/articles/16/3045/2024/ and PDF fetched; CC BY 4.0) |
| Dataset citation | Pourmohamad, Y. et al. (2023). Physical, Social, and Biological Attributes for Improved Understanding and Prediction of Wildfires: FPA FOD-Attributes Dataset (1.0) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.8381129 (version DOI; concept DOI 10.5281/zenodo.8381128). Published 2023-09-26, version 1.0, no newer version listed. |
| License | CC BY 4.0 (Zenodo API `license.id = cc-by-4.0`) |
| Download | Zenodo record https://zenodo.org/record/8381129 ; per-file API URLs of the form `https://zenodo.org/api/records/8381129/files/<name>/content` (used successfully) |
| Files | 29 annual CSVs `YYYY_FPA_FOD_cons.csv`, 125.5 MB (1997) to 258.3 MB (2006); one combined `FPA_FOD_Plus.csv` 5,025 MB. Total 10.1 GB. |
| Format | Plain CSV, 308 columns, one row per FPA FOD v6 record |
| Join key | `FOD_ID` (integer, unique) and `FPA_ID` are both carried in the file as columns 1 and 2. Also carried: `ICS_209_PLUS_INCIDENT_JOIN_ID`, `ICS_209_PLUS_COMPLEX_JOIN_ID`, `MTBS_ID`. |
| Temporal coverage | 1992-2020 (same as FPA FOD v6). Attribute-specific: GACC preparedness 2007-2020; MODIS NDVI/EVI 2000 onward; exotic grasses 2016-2021; SVI 2000/2010/2014/2016/2018/2020 (most recent prior year used); LANDFIRE EVC/EVT/EVH/FRG 2001/2012/2014/2016/2020 (most recent prior). |
| Spatial coverage | Attributes are computed for CONUS only. |

**Join test run on 2026-09-25** (file `1997_FPA_FOD_cons.csv`, 125,509,597 bytes, downloaded to the research scratch dir; duckdb, single thread):

| Check | Result |
|---|---|
| Rows in 1997 file / distinct FOD_ID | 61,442 / 61,442 |
| FPA FOD parquet rows with FIRE_YEAR = 1997 | 61,442 |
| Rows joined on FOD_ID | 61,442 (100%) |
| Attribute rows with no FPA FOD match | 0 |
| FIRE_SIZE mismatches after join | 0 |
| AK / HI / PR rows present in the file | 720 / 12 / 6 (attributes null for these; 738 = the 1.2% null rate seen on erc, bi, EVT, GAP_Sts etc.) |
| Null rate, 1997: erc, bi, vs, vpd, fm100, fm1000, pr, tmmx, rmin | 1.2% each (the non-CONUS rows) |
| Null rate, 1997: Elevation, Slope, FRG, NPL, GHM, GDP | 0.0% |
| Null rate, 1997: RPL_THEMES (SVI) | 0.2% |
| Null rate, 1997: No_FireStation_5.0km | 35.4% |
| Null rate, 1997: Evacuation | 85.4% |
| Null rate, 1997: road_county_dis / road_US_dis | 98.3% / 99.8% (see caveat 4) |
| Null rate, 1997: Population, GACC_PL, MOD_NDVI_12m | 100% (expected: WorldPop 2000+, GACC 2007+, MODIS 2000+) |
| GAP_Sts distribution, 1997 | 4: 48,562; 3: 8,534; 2: 2,273; 1: 1,335; null: 738 |
| Mang_Type distribution, 1997 | UNK 42,939; FED 10,478; TRIB 4,614; STAT 1,648; LOC 426; NGO 328; DIST 194 |

So the annual files contain every FPA FOD record for that year (including non-CONUS rows with empty attributes), and the FOD_ID join is exact. Expect about 2.2 million CONUS rows with attributes across all years (Zenodo description says "> 2.2 million wildfires from 1992-2020 in CONUS"); the repo parquet has 2,303,566 rows in total.

**Attribute groups** (from the paper's Table 1, the supplement's Table S1, and the file header; 308 columns = 37 FPA FOD fields + 267 added + `Year`, `LatLong_State`, `LatLong_County`, `geometry`):

| Group | Fields (as named in the CSV) | Source, resolution | Lens |
|---|---|---|---|
| Weather on discovery day | `pr, tmmn, tmmx, rmin, rmax, sph, vs, th, srad, etr, fm100, fm1000, bi, vpd, erc` | gridMET, 4 km, daily | a |
| 5-day window centred on discovery | `*_5D_mean` for all 15; `pr_5D_min/max, tmmn_5D_max, tmmx_5D_max, rmin_5D_min, rmax_5D_min, sph_5D_min, vs_5D_max, th_5D_max, srad_5D_max, etr_5D_max, fm100_5D_min, fm1000_5D_min, bi_5D_max, vpd_5D_max, erc_5D_max` | gridMET | a (note: the window includes 2 days after discovery; see caveat 5) |
| Climate normals and percentiles | `pr_Normal ... erc_Normal` (12); `tmmn/tmmx/sph/vs/fm100/bi/vpd/erc_Percentile` (categorical bins such as "50-70%") | gridMET climatologies 1990-2020 | a |
| Annual climate | `Annual_etr, Annual_precipitation, Annual_tempreture` (sic), `Aridity_index` | gridMET | a, c |
| Topography | `Elevation, Slope, Aspect, TPI, TRI` and `*_1km` means | LANDFIRE topographic, 30 m | a |
| Vegetation and fuel | `EVT, EVC, EVH` (point) and `EVT_1km, EVC_1km, EVH_1km` (most frequent / mean in 1 km); `FRG, FRG_1km`; `Land_Cover, Land_Cover_1km` (NLCD); `rpms, rpms_1km` (rangeland production); `CheatGrass, ExoticAnnualGrass, Medusahead, PoaSecunda` (2016-2021 only); `MOD_NDVI_12m, MOD_EVI_12m` (MODIS monthly, 12 months prior, 2000+); `NDVI-1day, NDVI_min/max/mean` (NOAA CDR) | LANDFIRE 30 m; NLCD 30 m; MODIS 5.6 km; AVHRR/VIIRS 5.55 km | a, b |
| Protection status | `GAP_Sts` (1-4), `GAP_Prity`, `Mang_Type` (FED, STAT, LOC, TRIB, NGO, DIST, UNK), `Mang_Name`, `Des_Tp` (designation type, e.g. Wilderness Area) | PAD-US 3.0 (supplement cites doi 10.5066/P9Q9LQ4B) | b |
| Ecoregions | `Ecoregion_US_L4CODE, US_L3CODE, NA_L3CODE, NA_L2CODE, NA_L1CODE`; `NAME` (pyrome) | EPA Omernik; Short et al. pyromes | a, b, c |
| Social | `RPL_THEMES, RPL_THEME1-4, EPL_*` (CDC SVI, tract); `TRACT`; 107 CEJST fields (`*_PFS`, `*_ET`, `*LI`, etc.); `Population, Popo_1km` (WorldPop, 2000+); `GDP` (per capita, 1990/2000/2015); `GHM` (global human modification) | tract; 100 m; 9.3 km; 1 km | b, c |
| Suppression context | `No_FireStation_1.0/5.0/10.0/20.0km` (HIFLD); `road_county_dis, road_interstate_dis, road_common_name_dis, road_other_dis, road_state_dis, road_US_dis` (m, TIGER); `SDI` (suppression difficulty index) and `Evacuation` (hours to hospital) from USFS Risk Management Assistance; `NPL` (national preparedness level, daily); `GACCAbbrev, GACC_PL, GACC_New fire, GACC_New LF, GACC_Uncont LF, GACC_Type 1 IMTs, GACC_Type 2 IMTs, GACC_NIMO Teams, GACC_Area Command Teams, GACC_Fire Use Teams` (2007-2020) | point / vector / raster / daily | a |
| Geometry | `geometry` as WKT `POINT (x y)` in projected metres (values around 1.2e6, 1.2e6; CRS not stated in paper or supplement) | | use `LATITUDE`/`LONGITUDE` (NAD83) instead |

**Caveats the authors state** (ESSD paper, section 5, fetched):
1. Accuracy, precision and uncertainty of each attribute depend on the source data; availability depends on the source's spatial and temporal coverage.
2. FPA FOD location precision is only guaranteed to a PLSS section (1 square mile, 2.6 km2), and "the locations of many smaller fires overseen by local jurisdictions may reflect the reporting location rather than the ignition location". With 30 m LANDFIRE and 100 m WorldPop sampled at the point, this matters; prefer the `_1km` versions where they exist.
3. Some duplicate records may remain despite QA.
4. The dataset "does not provide details about large fire growth days that may have occurred days to weeks from the ignition date"; pair with ICS-209-PLUS for growth.
5. No support for smoke or emissions analyses.
6. The authors recommend careful variable selection for ML because "variables have substantial overlap and correlation".

**Caveats found in this session's checks** (not stated by the authors):
1. Attributes are CONUS-only. Alaska rows (720 in 1997) are present but empty, so an Alaska-inclusive model needs a separate weather source or must drop Alaska.
2. The 5-day window statistics are centred on the discovery date, so `*_5D_*` fields use two days of weather after discovery. For a model that must only use information known at discovery, use the same-day fields (`erc`, `vs`, etc.) and the normals/percentiles, not the 5D fields.
3. `road_*_dis` fields are 98-99.8% null in 1997; the supplement gives no search radius or reason. Check other years before relying on them.
4. `No_FireStation_5.0km` is 35% null and `Evacuation` 85% null in 1997; the Risk Management Assistance rasters are CONUS-wide but apparently sparse.
5. The `geometry` column is in an unstated projected CRS; the paper says nothing about it.
6. The dataset fixes PAD-US at version 3.0 and LANDFIRE at the most recent release before the fire; it will not track PAD-US 4.x or LF 2023+.

Effort: **S** to load one year, **M** to build a full 29-year Parquet (download 10.1 GB of annual CSVs, keep about 60 columns, join on FOD_ID; the 4-CPU box handles one 200 MB CSV at a time in under a minute with duckdb).

The supplement (Table S1, 40 pages) is saved at the research scratch dir as `essd_supplement.pdf` and `essd_supplement.txt`; the paper as `essd-16-3045-2024.pdf`; the 1997 file as `1997_FPA_FOD_cons.csv`; the Zenodo API response as `zenodo_8381129.json`.

---

## FPA FOD 6th edition itself (Short 2022)

| Item | Verified value |
|---|---|
| Citation | Short, Karen C. 2022. Spatial wildfire occurrence data for the United States, 1992-2020 [FPA_FOD_20221014]. 6th Edition. Fort Collins, CO: Forest Service Research Data Archive. https://doi.org/10.2737/RDS-2013-0009.6 |
| Catalog page | https://www.fs.usda.gov/rds/archive/Catalog/RDS-2013-0009.6 (verified): ACCDB 172 MB, GDB 136 MB, GPKG 211 MB, SQLite 214 MB |
| Metadata | https://www.fs.usda.gov/rds/archive/products/RDS-2013-0009.6/_metadata_RDS-2013-0009.6.html (verified) |
| Inclusion rule | "discovery date, final fire size, and a point location at least as precise as Public Land Survey System (PLSS) section" |
| Completeness statements | "Viable state and local (i.e., nonfederal) records were not available from all states for all years." States were scored for completeness; "High-scoring states include most of those in the U.S. Great Lakes, Southeastern, and Western regions." "Estimates of area burned tend to be less compromised than wildfire numbers by missing nonfederal records, because very large fires tend to account for the majority of area burned." |
| Cause standard | Transformed to the NWCG cause standard approved August 2020 (the 13 `NWCG_GENERAL_CAUSE` values) |
| Join fields | `MTBS_ID` = "Incident identifier, from the MTBS perimeter dataset"; `ICS_209_PLUS_INCIDENT_JOIN_ID` = "Primary identifier needed to join into operational situation reporting data for the incident in the ICS-209-PLUS dataset"; `ICS_209_PLUS_COMPLEX_JOIN_ID` = secondary identifier for complexes, "2014 and later only" (supplement Table S1) |
| `CONT_DATE` definition | "Date on which the fire was declared contained or otherwise controlled" |

Lens: a, b, c. Effort: already done.

---

## Weather and climate

### gridMET (Abatzoglou 2013)
- Adds: daily surface weather and NFDRS fire danger for CONUS, 1979 to present, on a 4 km grid; the same source FPA FOD-Attributes used. Needed only if you want variables or windows the Attributes file does not carry (for example, a strictly pre-discovery 3-day window, or Alaska, which gridMET does not cover either).
- Resolution: 4 km (1/24 degree), daily, 1979 to 2026 (files through 2026-09-24 present in the directory listing).
- Variables (verified on https://www.climatologylab.org/gridmet.html): `tmmx, tmmn, pr, sph, rmin, rmax, vs, th, srad, etr, pet, erc, bi, fm100, fm1000, vpd, pdsi`; the direct-download directory also has `spi` and `spei` at several time scales and `z` (elevation).
- Access: direct netCDF download https://www.northwestknowledge.net/metdata/data/ (verified; naming `<var>_<year>.nc`; erc_2020.nc 84 MB, pr_2020.nc 56 MB, vs_2020.nc 59 MB, tmmx_2020.nc 140 MB); THREDDS/OpenDAP catalogs (aggregated and standard) linked from the gridMET page; also Google Earth Engine and ClimateEngine. Climatologies catalog cited by the Attributes supplement: http://thredds.northwestknowledge.net:8080/thredds/catalog/MET/climatologies/catalog.html (not fetched; unverified).
- Format: NetCDF4 with scale/offset.
- License: public domain (CC0) per the gridMET page.
- Join: nearest 4 km cell to LATITUDE/LONGITUDE on DISCOVERY_DATE; xarray with `sel(method='nearest')` per point-day. For 2.3 M points it is a vectorised indexing job per variable-year file (about 1.4 GB per variable for 29 years).
- Citation: Abatzoglou, J. T. (2013). Development of gridded surface meteorological data for ecological applications and modelling. International Journal of Climatology 33: 121-131. https://doi.org/10.1002/joc.3413 (Crossref verified).
- Effort: M (only for windows not in Attributes). Lens: a.

### GHCN-Daily (NCEI)
- Adds: station observations (PRCP, TMAX, TMIN, SNOW, SNWD; AWND and others at some stations). Useful as a ground-truth check on gridMET at a few sites, not as a primary predictor: coverage is uneven and half of stations report precipitation only.
- Access: https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/ (verified; `access/`, `archive/`, `doc/`); readme https://www.ncei.noaa.gov/pub/data/ghcn/daily/readme.txt (verified: `.dly` fixed-width, `ghcnd-all.tar.gz`, `ghcnd-stations.txt`, `by_year`). Product page https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily (verified).
- License: NOAA data, cite as "GHCN-Daily, Version 3, doi:10.7289/V5D21VHZ" per the readme.
- Join: nearest station within a radius, by date; needs station QC. Effort: M. Lens: c (validation only).

### ERA5-Land (Copernicus)
- Adds: global hourly reanalysis on 0.1 degree (9 km) grid, 1950 to present, including Alaska (which gridMET lacks). GRIB or NetCDF via the CDS API. CC BY licence. DOI 10.24381/cds.e2161bac. Page https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land (verified).
- Join: nearest cell by point and hour; requires CDS account and API key, and volumes are large (hourly). Only worth it for an Alaska extension. Effort: L. Lens: a (Alaska only).

### US Drought Monitor
- Adds: weekly categorical drought (D0-D4) polygons, plus county/state statistics; start year 2000 per NDMC (the data-download page verified lists comprehensive statistics, DSCI, thresholds, weeks-in-drought; GIS page lists shapefile, KML, GeoJSON, WMS). https://droughtmonitor.unl.edu/DmData/DataDownload.aspx and https://droughtmonitor.unl.edu/DmData/GISData.aspx (both verified).
- Citation requirement: NDMC, USDA and NOAA.
- Join: point-in-polygon on the weekly map preceding discovery; or county FIPS join on the county statistics (FPA FOD has FIPS_CODE for many rows).
- Note: Riley et al. 2013 (LITERATURE.md) found long-term drought indices are weak predictors of large-fire occurrence relative to ERC; the Attributes file already carries `fm1000` and `erc` percentiles which do the same job daily and back to 1992. Effort: M. Lens: c.

### SPEI / PDSI
- gridMET distributes `pdsi`, `spi` and `spei` at several time scales in the same directory as the daily variables (directory listing verified). SPEIbase at https://spei.csic.es/database.html was reachable (HTTP 200 by curl HEAD) but the page did not load in WebFetch; treat details as unverified. Prefer gridMET's versions. Effort: S once gridMET tooling exists. Lens: a (secondary), c.

---

## Fuels, vegetation, terrain

### LANDFIRE
- Adds: EVT (existing vegetation type), FBFM40 (Scott and Burgan fuel models), canopy cover/height, fire regime group, topography, all at 30 m. Latest full-extent release is LF 2025 (page verified: https://landfire.gov/data/FullExtentDownloads); FBFM40 CONUS zips are 1.14 to 3.28 GB per version; EVT page https://landfire.gov/vegetation/evt (verified). LF Product Service API at https://lfps.usgs.gov/ (linked, not fetched).
- Not in FPA FOD-Attributes: FBFM40 and canopy cover/height. Everything else (EVT, EVC, EVH, FRG, topography) is already there.
- License: not stated on the download page; USGS/USFS public data.
- Join: point sample of the 30 m raster (rasterio `sample`), ideally the version dated before the fire year. Effort: M per product (multi-GB rasters). Lens: a (FBFM40 is the one worth adding; the WildfireIA benchmark found fuel the strongest static predictor), b.

### USGS 3DEP elevation
- Adds: 1/3 arc-second (about 10 m) and 1 arc-second (about 30 m) DEMs, 1 m where available; GeoTIFF; "free of charge and without use restrictions" (https://www.usgs.gov/3d-elevation-program and /about-3dep-products-services, both verified). Access via The National Map, AWS public bucket, and the EPQS point query service.
- Redundant with the LANDFIRE-derived `Elevation, Slope, Aspect, TPI, TRI` in Attributes. Only needed for Alaska or for a finer DEM. Effort: M. Lens: a (optional).

### NLCD (MRLC)
- Adds: Annual NLCD Collection 1.2, land cover, impervious surface, tree canopy, 30 m, 1985-2025 CONUS (https://www.mrlc.gov/data verified). Attributes carries NLCD `Land_Cover` and top classes in 1 km already (1992, 2001, 2004-2019 releases). The annual product would let you use the year before each fire consistently. Effort: M. Lens: b, c.

---

## Fire outcome and perimeter datasets

### MTBS (Monitoring Trends in Burn Severity)
- Adds: perimeters and burn-severity mosaics for fires of at least 1,000 acres in the West and 500 acres in the East (Alaska and Hawaii use the western threshold, Puerto Rico the eastern), 1984 to present, released roughly quarterly (https://www.mtbs.gov/ and https://www.mtbs.gov/faqs verified). Products: burned area boundaries (polygon shapefile, `mtbs_perimeter_data.zip`), fire occurrence points, burn severity mosaics (GeoTIFF), per-fire bundles (https://www.mtbs.gov/product-descriptions verified). Thresholds capture "approximately 95% of the annual area burned".
- Join: FPA FOD `MTBS_ID` equals the MTBS `Event_ID`. This is a direct key join, no spatial work. The Attributes file carries `MTBS_ID` through.
- Use: (a) as a label source for "large fire" that is independent of the reported `FIRE_SIZE`; (b) severity (dNBR classes) inside protected areas for the conservation lens; (c) area-burned trends that do not depend on nonfederal reporting (Dennison et al. 2014 used it for that reason).
- Download URL: the consolidated site https://burnseverity.cr.usgs.gov/direct-download (loads, but the download links are behind a JavaScript app; not verified beyond the page existing). Terms not stated on the pages fetched.
- Effort: S for the ID join, M for severity rasters. Lens: a, b, c.

### ICS-209-PLUS (St. Denis et al. 2023)
- Adds: daily incident status reports (sitreps) for 34,478 wildland fires 1999-2020: structures destroyed/damaged/threatened, personnel, estimated cost, evacuations, fire spread rate, containment progression. Paper: St. Denis, L. A., Short, K. C., McConnell, K., Cook, M. C., Mietkiewicz, N. P., Buckland, M., and Balch, J. K. (2023). All-hazards dataset mined from the US National Incident Management System 1999-2020. Scientific Data 10: 112. https://doi.org/10.1038/s41597-023-01955-0 (PMC copy https://pmc.ncbi.nlm.nih.gov/articles/PMC9958120/ verified; Crossref verified).
- Data: figshare https://doi.org/10.6084/m9.figshare.19858927.v3 (API verified): `ics209plus-wildfire.zip` 48.7 MB, `ics209plus-allhazards.zip` 40.5 MB, `ics209plus-source.zip` 426.9 MB, `ics209plus-reference.zip` 0.1 MB; CC BY 4.0; version 3, 2023-01-10. (The older 1999-2014 release is figshare 8048252, v14, CC0, 2020.)
- Join: FPA FOD `ICS_209_PLUS_INCIDENT_JOIN_ID` to the incident-level table's incident ID (the paper says about 86% of ICS-209 incidents link to FPA FOD). Also links to MTBS.
- Use: this is the only source with daily growth and containment percent, so it is the right target source for "days to containment" on fires that had an ICS-209, and the right place to get a "structures destroyed" outcome. It covers only incidents large enough to file a 209, so it is a biased subset of FPA FOD.
- Effort: S (tabular key join). Lens: a (outcome labels), c.

### NIFC WFIGS (IRWIN-based incident locations and perimeters)
- Adds: current-era incident records with `FireDiscoveryDateTime`, `ContainmentDateTime`, `ControlDateTime`, `FireOutDateTime`, `InitialResponseAcres`, `PercentContained`, `FireCause*`, `POO*` jurisdiction fields, `IrwinID` (field list verified from the ArcGIS REST service `WFIGS_Incident_Locations`, layer 0, at https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/). Services listed include `WFIGS_Incident_Locations`, `WFIGS_Interagency_Perimeters`, `WFIGS_Interagency_Perimeters_Certified`, `InteragencyFirePerimeterHistory_*` by decade, and `WFDSS_InteragencyFirePerimeterHistory_AllYears`.
- Join to FPA FOD: none direct. FPA FOD ends in 2020; WFIGS is the post-2020 continuation of the same reporting stream (IRWIN). It is the source for extending the descriptive story past 2020 and for any real-world "score a new fire at discovery" demo. Terms: ArcGIS Hub open data (license not read; unverified).
- Effort: M. Lens: c, and a for a forward-in-time test on 2021+ fires.

### WFDSS
- Not reachable in this session (404 and connection reset). Decision-support system requiring an account; its perimeter history is republished through the NIFC service above. Unverified; do not plan on it.

---

## Protection, habitat, community exposure (conservation lens)

### PAD-US (USGS GAP)
- Adds: the national inventory of protected areas with `GAP_Sts` 1-4, manager type and name, designation type, and access. Current versions 4.0 and 4.1 (2024); DOI https://doi.org/10.5066/P96WBCHS ; geodatabase, shapefiles, web services (https://www.usgs.gov/programs/gap-analysis-project/science/pad-us-data-overview verified). GAP status definitions (verified): 1 permanent protection, natural disturbance allowed (Wilderness, some National Parks); 2 permanent protection, natural state managed (refuges, Nature Conservancy preserves); 3 permanent protection but extractive uses allowed (National Forests, BLM); 4 no known protection mandate.
- Already in Attributes as PAD-US 3.0 fields (`GAP_Sts`, `Mang_Type`, `Des_Tp`, `GAP_Prity`). Re-joining PAD-US 4.1 only matters if you want current boundaries or the full designation inventory rather than the prioritised raster.
- Join: point-in-polygon. Effort: S using Attributes, M for a fresh 4.1 join (the national GDB is large). Lens: b.

### USFWS critical habitat
- Adds: final critical habitat polygons and lines for ESA-listed species. National shapefile zip `https://ecos.fws.gov/docs/crithab/crithab_all/crithab_all_shapefiles.zip` responded HTTP 200 with content-length 417,703,162 bytes (398 MB) on HEAD (verified); ScienceBase item https://www.sciencebase.gov/catalog/item/50a412c1e4b0855e233c07da (verified; shapefile, ArcGIS REST, WMS). Terms not stated.
- Join: point-in-polygon of ignition points; count fires and acres inside designated habitat by species group. Effort: M. Lens: b.

### SILVIS WUI change 1990-2020 (Radeloff et al.)
- Adds: census-block WUI classification (intermix, interface) for 1990, 2000, 2010, 2020; shapefiles by state and a national GDB; version 4, updated February 2025; https://silvis.forest.wisc.edu/data/wui-change/ (verified); download https://geoserver.silvis.forest.wisc.edu/geodata/wui_change_2020_v4/ (linked, not fetched). Citation: Radeloff, V. C. et al. (2018). Rapid growth of the US wildland-urban interface raises wildfire risk. PNAS 115(13): 3314-3319. https://doi.org/10.1073/pnas.1718850115 (Crossref and Europe PMC verified).
- Not in Attributes. Join: point-in-block polygon using the decade nearest the fire year. Effort: M (national block layer is heavy; do it per state). Lens: a (human-ignition context), b, c.

### Wildfire Risk to Communities (USFS, 2nd edition, 2024)
- Adds: 30 m rasters of burn probability, wildfire hazard potential, conditional flame length, risk to potential structures, exposure type, plus population/housing layers; based on LANDFIRE 2020 with disturbances through 2022. Citation: Scott, J. H., Dillon, G. K., Jaffe, M. R., Vogler, K. C., Olszewski, J. H., Callahan, M. N., Karau, E. C., Lazarz, M. T., Short, K. C., Riley, K. L., Finney, M. A., Grenfell, I. C. 2024. Wildfire Risk to Communities: Spatial datasets of landscape-wide wildfire risk components for the United States. 2nd Edition. Forest Service Research Data Archive. https://doi.org/10.2737/RDS-2020-0016-2 (verified). Terms: "can be used without additional permissions or fees". Portal https://wildfirerisk.org/download/ (verified).
- Caution for the model: burn probability is itself a modelled output built partly from FPA FOD ignitions and simulated spread; using it as a predictor of large-fire probability is circular for 1992-2020 fires. It is fine as descriptive context and for the conservation lens.
- Effort: M. Lens: b, c.

### FEMA National Risk Index
- Adds: county and tract scores for 18 hazards including wildfire (expected annual loss, social vulnerability, community resilience). Version 1.20, December 2025; CSV, shapefile, geodatabase; zips 39 MB to 411 MB; https://www.fema.gov/about/openfema/data-sets/national-risk-index-data and https://www.fema.gov/flood-maps/products-tools/national-risk-index (both verified). Terms are on the tracts page (not read).
- Join: `FIPS_CODE` (county) from FPA FOD, or tract from Attributes `TRACT`. Descriptive only; its wildfire component is also derived from modelled burn probability. Effort: S. Lens: c.

### CDC/ATSDR SVI
- Adds: tract and county social vulnerability for 2000, 2010, 2014, 2016, 2018, 2020, 2022; four themes; `RPL_THEMES`, `RPL_THEME1-4`, `EPL_*` fields (https://www.atsdr.cdc.gov/place-health/php/svi/svi-data-documentation-download.html verified). Already in Attributes through 2020. Effort: S. Lens: b, c.

### Census TIGER/Line and ACS
- Adds: tract, county, place and road geometries 1992-2025 (shapefiles from 2007; 2025 release 2025-09-23; public domain; https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html verified). Roads are the source of the Attributes `road_*_dis` fields, which were nearly all null in 1997; a fresh nearest-road distance from TIGER primary/secondary roads is a well-known predictor of human ignition and an S-M job with a spatial index. Effort: M. Lens: a, c.

---

## Lightning

### NLDN (Vaisala) via NCEI
- Raw NLDN flash data are restricted to NOAA employees and contractors (https://www.ncei.noaa.gov/products/lightning-products verified). Publicly available: SWDI daily cloud-to-ground flash counts in 0.1 degree tiles, daily county and state flash-count summaries (CSV via HTTPS), and GOES GLM (2017+). Do not plan on raw NLDN.
- Join: county-day flash counts to FPA FOD by `FIPS_CODE` and `DISCOVERY_DATE`; useful as a check on the "Natural" cause label and as a predictor of lightning-fire clustering (holdover fires). Effort: M. Lens: a (secondary), c.

### NOAA Storm Events Database
- Adds: NWS-reported events 1950-2026 including Lightning and Wildfire event types, with damage and casualty fields; bulk CSVs at https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/ (verified; `StormEvents_details-ftp_v1.0_dYYYY_cYYYYMMDD.csv.gz`; 2020 details about 10.4 MB). Event reporting is uneven and narrative-driven; use for context only. Effort: S. Lens: c.

---

## Others considered

- NASA FIRMS (MODIS/VIIRS active fire detections): not fetched this session (unverified). The WildfireIA benchmark (LITERATURE.md) used VIIRS detections aligned to FPA FOD fires as the "least redundant" data source; VIIRS starts in 2012, so it would only cover the last 9 years of FPA FOD.
- USFS Risk Management Assistance rasters (SDI, evacuation time): only reachable through a SharePoint link in the Attributes supplement; use the Attributes fields.
- HIFLD fire stations: source of `No_FireStation_*` in Attributes; not fetched separately.

---

## Which sources each lens needs

| Lens | Required | Nice to have |
|---|---|---|
| (a) Large-fire probability at discovery | FPA FOD; FPA FOD-Attributes (same-day gridMET, normals, percentiles, topography, EVT/EVC/EVH/FRG, GAP_Sts, fire stations, NPL/GACC); MTBS_ID as an alternative label | LANDFIRE FBFM40; fresh TIGER road distance; SILVIS WUI; ICS-209-PLUS for a containment-time target on 209 fires; WFIGS 2021+ for a forward test |
| (b) Conservation lens | FPA FOD-Attributes GAP_Sts/Mang_Type/Des_Tp and ecoregions; MTBS perimeters and severity; USFWS critical habitat | PAD-US 4.1; NLCD annual; Wildfire Risk to Communities |
| (c) Descriptive context | FPA FOD; MTBS (area-burned trend that does not depend on nonfederal reporting); SILVIS WUI | FEMA NRI, SVI, USDM, Storm Events, lightning county summaries, WFIGS for post-2020 |

---

## Recommended order of adoption

1. **FPA FOD-Attributes (Zenodo 10.5281/zenodo.8381129).** It is verified, CC BY 4.0, joins 100% on FOD_ID (tested on 1997), and delivers same-day gridMET fire weather, climate normals and percentiles, topography, LANDFIRE vegetation, PAD-US GAP status, SVI, fire-station counts and preparedness levels in one table. This replaces the README's "join NOAA weather" next step and most of the conservation-lens joins. Build a 29-year Parquet of about 60 selected columns from the annual files (10.1 GB download, done one year at a time). Drop the `*_5D_*` fields from any at-discovery model and drop Alaska/Hawaii/Puerto Rico rows or model them separately.

2. **MTBS via the existing `MTBS_ID` key.** Zero spatial work, gives an outcome label ("became an MTBS-mapped fire", i.e. at least 1,000 acres West or 500 acres East) that is independent of reported `FIRE_SIZE`, plus perimeters and severity for the conservation lens and an area-burned trend series that is less exposed to the nonfederal reporting gaps Short documents.

3. **ICS-209-PLUS via `ICS_209_PLUS_INCIDENT_JOIN_ID`.** Tabular, CC BY 4.0, 49 MB for the wildfire subset. It is the only source with daily containment percent, personnel and structures destroyed, so it is where a defensible "days to containment" or "structures lost" target lives, with the explicit caveat that it covers only fires that filed a 209. It also answers the Control Efficiency Score problem in the README: response can be measured with personnel and containment progression rather than acres per hour.

After these three: SILVIS WUI (human-ignition and exposure context), LANDFIRE FBFM40 (the one fuel variable the Attributes file lacks), USFWS critical habitat (conservation lens), and WFIGS (post-2020 continuation and a true forward-in-time test).
