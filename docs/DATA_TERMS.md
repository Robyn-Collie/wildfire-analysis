# Data terms and attribution

The code in this repository is MIT licensed (`LICENSE`). The data are not. Every number, table, figure and site page here is an aggregate derived by this project from the sources below, and the sources' own terms apply to them. None of the source agencies or authors reviewed or endorse this analysis.

## FPA FOD, 6th edition (the fire records)

- **Citation:** Short, Karen C. 2022. *Spatial wildfire occurrence data for the United States, 1992-2020 [FPA_FOD_20221014].* 6th Edition. Fort Collins, CO: Forest Service Research Data Archive. https://doi.org/10.2737/RDS-2013-0009.6
- **Terms (from the archive's metadata record, fetched 2026-09-25):** "These data were collected using funding from the U.S. Government and can be used without additional permissions or fees." Access constraints: none.
- **Liability (same record, verbatim):** "neither the author, the Archive, nor any part of the federal government can assure the reliability or suitability of these data for a particular purpose."
- **What this project does with it:** reads the SQLite file (SHA-256 in `data.sha256`), derives per-state, per-year, per-cause and per-cell aggregates, and publishes those aggregates and figures. The raw records are not redistributed. The database's own completeness statement applies to everything built on it: counts "may underrepresent actual wildfire activity in certain areas and time periods."

## FPA FOD-Attributes (weather, fuels, terrain, protection status, social context)

- **Citation:** Pourmohamad, Y., Abatzoglou, J. T., Belval, E. J., Fleishman, E., Short, K., Reeves, M. C., Nauslar, N., Higuera, P. E., Henderson, E., Ball, S., AghaKouchak, A., Prestemon, J. P., Olszewski, J., and Sadegh, M. 2024. Physical, social, and biological attributes for improved understanding and prediction of wildfires: FPA FOD-Attributes dataset. *Earth System Science Data* 16: 3045-3060. https://doi.org/10.5194/essd-16-3045-2024. Data: https://doi.org/10.5281/zenodo.8381129 (version 1.0).
- **License:** CC BY 4.0.
- **What this project does with it:** joins about 80 of its 308 columns to the fire records on `FOD_ID` for 2010-2020 to train and evaluate the large-fire probability model. Its own sources (gridMET, LANDFIRE, NLCD, PAD-US 3.0, CDC SVI, WorldPop and others) are credited in the paper.

## ICS-209-PLUS (incident outcomes)

- **Citation:** St. Denis, L. A., Short, K. C., McConnell, K., Cook, M. C., Mietkiewicz, N. P., Buckland, M., and Balch, J. K. 2023. All-hazards dataset mined from the US National Incident Management System 1999-2020. *Scientific Data* 10: 112. https://doi.org/10.1038/s41597-023-01955-0. Data: https://doi.org/10.6084/m9.figshare.19858927.v3.
- **License:** CC BY 4.0.
- **What this project does with it:** joins incident-level structures, personnel and cost fields to fire records on `ICS_209_PLUS_INCIDENT_JOIN_ID`.

## PAD-US 4.1 (protected areas)

- **Citation:** U.S. Geological Survey Gap Analysis Project. 2024. *Protected Areas Database of the United States (PAD-US) 4.1.* https://doi.org/10.5066/P96WBCHS (check `docs/DATA_JOINS.md` for the exact DOI used).
- **Terms:** USGS data, no fee; the USGS notes PAD-US is not authoritative for regulatory use.
- **What this project does with it:** assigns a protection status (GAP code) and manager type to each ignition point.

## Other sources

`docs/DATA_JOINS.md` records every external file this project downloads, with URL, license, size, SHA-256 and download date. `docs/research/DATA_SOURCES.md` records the sources considered and their terms.

## How to cite this project

Robyn Collie, *wildfire-analysis*, https://github.com/Robyn-Collie/wildfire-analysis, with the data citations above. Please cite the data sources whenever you reuse a number from this repository.
