# The first us-wildfires site (archived)

This folder is the source of the first public us-wildfires site, which ran at us-wildfires.netlify.app from
July to September 2026. It was replaced by the site in `site/` on 2026-09-28, and it is still served, read-only,
at [us-wildfires.netlify.app/archive/](https://us-wildfires.netlify.app/archive/). Its claims are audited in
`docs/review/V1_SITE_AUDIT.md`.

It was built in a separate local repository (`wildfire-poc`, last commit `7793b54`). This is a snapshot of that
repository's files, not its history, with these left out:

- the map point files (`site-v2/public/data/points-v2.bin`, `explore-cause13.bin`, `site/hero-data/points.bin`)
  and the typed data caches (`data/*.parquet`), which follow this repository's no-data-in-git rule;
- the agent prompts and the local planning notes (`prompts/`, `PLAN.md`, `REDESIGN.md`, `build-log.md`,
  `design-spec*.md`, `research/`, `replay/`). The public, redacted build record is the replay on
  agent-built-demos.netlify.app.

`site-v2/` is the Astro source of the version that was live last (the map console with the factual copy pass).
`site/` is the earlier plain-HTML version. `pipeline/` and `analysis/` produced their data files.

The archive that is deployed is not rebuilt from here. It is the built output, rewritten to live under
`/archive/` by `scripts/archive_v1.py`, and committed in `deploy/archive/` without its binary data files, which `scripts/deploy.py` takes from `data/archive_v1/`.
