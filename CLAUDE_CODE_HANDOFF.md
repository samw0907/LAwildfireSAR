# Claude Code Handoff — LA Wildfire SAR Project
## Status as of 2026-06-26 — PIPELINE AND OUTPUTS COMPLETE

This file is the handoff document for the next Claude Code session.
Read this fully before doing anything. The project is in a clean, complete state.
The primary outstanding task is **S3 output sync**, which was always planned but not yet implemented.

---

## Project Overview

Production-grade SAR wildfire damage assessment pipeline built in Python.
Detects building-level structural damage from the January 2025 LA wildfires (Eaton and Palisades fires)
using free Sentinel-1 SAR imagery, validated against CAL FIRE DINS ground truth.

Portfolio piece targeting ICEYE GIS Operational Analyst role — methodology and documentation
are written to that standard throughout.

**Repo:** github.com/samw0907/LAwildfireSAR  
**Local:** `C:\Users\swill\dev\LAwildfireSAR`  
**Python:** 3.14 on Windows. Run all scripts from project root. Use `python -m pip install`, not `pip install`.  
**SNAP GPT** must be on PATH for RTC processing (already done; data is already processed).

---

## Everything Completed This Session

### Pipeline stages — all complete, outputs on disk

```
[✓] Download + SNAP RTC     6 × Sentinel-1 Track 64 scenes
[✓] Composite               Pre/post VV+VH, median stack, single master reference grid
[✓] Change detection        change_combined.tif, burn_perimeter_full.geojson
[✓] Buildings               building_damage_eaton.geojson, building_damage_palisades.geojson
[✓] Validate                Threshold calibrated 3.0 → 2.9 dB, converged
[✓] Visualisations          9 figures in outputs/figures/
[✓] README.md               Comprehensive portfolio README with all figures embedded
```

### Final validation results (2.9 dB calibrated threshold)

| Event | Precision | Recall | F1 | Accuracy | Validated on |
|-------|-----------|--------|----|----------|--------------|
| Eaton | 0.749 | 0.868 | 0.804 | 0.732 | 5,992 buildings |
| Palisades | 0.723 | 0.893 | 0.799 | 0.736 | 6,220 buildings |

### Building damage counts

| Event | Destroyed | Possibly Affected | No Damage | No Data | Total |
|-------|-----------|-------------------|-----------|---------|-------|
| Eaton | 2,126 | 1,198 | 1,156 | 6,047 | 10,527 |
| Palisades | 2,583 | 1,307 | 1,468 | 3,985 | 9,343 |

No data rate (~50%) is an inherent Sentinel-1 20m resolution limitation — buildings without
a pixel centroid within their footprint cannot be classified. Documented in README as per
UNOSAT/Copernicus EMS standard practice. `all_touched=True` and buffering were considered
and rejected (neighbourhood backscatter contamination — not industry standard).

---

## Output Figures (outputs/figures/)

| File | Contents |
|------|----------|
| `damage_map_eaton.png` | Full perimeter, buildings coloured by damage class, statistics inset |
| `damage_map_palisades.png` | Same for Palisades |
| `damage_zoom_eaton.png` | 2.5 km zoom on most-damaged neighbourhood, individual polygons visible |
| `damage_zoom_palisades.png` | Same for Palisades |
| `damage_map_combined.png` | Both fires, geographic context, LA basin |
| `sar_panel_eaton.png` | 3 panels: pre SAR backscatter / post SAR backscatter / change + classification |
| `sar_panel_palisades.png` | Same for Palisades |
| `validation_metrics.png` | Confusion matrices + precision/recall/F1 bars |
| `change_signal_dist.png` | Violin plots: SAR signal separability by DINS damage category |

All figures are referenced in README.md.

---

## Data State

```
data/raw/           6 × Track 64 SAFE zips ✓ + 6 × old Track 137 zips (safe to leave)
data/rtc/           18 × Track 64 TIFs ✓ (VV + VH + localIncidenceAngle per scene)
                    Old Track 137 RTC TIFs also present — no date overlap, no conflict
data/analysis/      pre/post composites VV+VH ✓, change_combined.tif ✓
data/vectors/       building_damage_eaton.geojson ✓
                    building_damage_palisades.geojson ✓
                    burn_perimeter_full.geojson ✓
data/validation/    validation_summary.json ✓
outputs/figures/    9 PNG figures ✓
README.md           ✓
```

---

## OUTSTANDING TASK — S3 Output Sync

This was planned from the start (AWS config already in `config/pipeline_config.yaml`) but not yet implemented.

### Config already in place

```yaml
aws:
  bucket: sam-sar-wildfire
  prefix: la-wildfires-2025
  region: eu-north-1
```

`boto3` is already installed. AWS credentials will need to be in `.env` or `~/.aws/credentials`.

### What needs to be built

A `scripts/sync_to_s3.py` (or `src/pipeline/s3_sync.py`) that uploads the final outputs to S3.
The scope of what to sync is a decision for the next session — options:

1. **Outputs only** (recommended starting point) — upload `outputs/figures/`, `data/vectors/`, `data/validation/`
2. **Full pipeline outputs** — also include `data/analysis/` (composites, change raster ~several GB)
3. **Everything** — including `data/rtc/` (~30+ GB, probably not needed in S3)

Suggested structure on S3:
```
s3://sam-sar-wildfire/la-wildfires-2025/
    vectors/
        building_damage_eaton.geojson
        building_damage_palisades.geojson
        burn_perimeter_full.geojson
    validation/
        validation_summary.json
    figures/
        damage_map_eaton.png
        damage_map_palisades.png
        damage_zoom_eaton.png
        damage_zoom_palisades.png
        damage_map_combined.png
        sar_panel_eaton.png
        sar_panel_palisades.png
        validation_metrics.png
        change_signal_dist.png
    analysis/          (optional — large files)
        change_combined.tif
        pre_composite_VV.tif
        post_composite_VV.tif
        pre_composite_VH.tif
        post_composite_VH.tif
```

The sync script should:
- Use `boto3` with the bucket/prefix/region from `pipeline_config.yaml`
- Support a `--dry-run` flag to list what would be uploaded without uploading
- Skip files already on S3 if the local MD5/ETag matches (avoid re-uploading unchanged files)
- Print progress per file
- Handle large GeoTIFF uploads gracefully (multipart upload for files > 100 MB)

---

## Key Methodology Decisions Made This Session (for context)

### Fix 1 — Eaton NaN root cause
Track 137 IW3 burst boundary at x≈392,200m UTM 11N; Eaton perimeter starts at x=392,938m.
Switched to **Track 64** which places both fires in swath interior. Full coverage confirmed.

**New scenes:** Pre 2024-12-04/16/28, Post 2025-01-21/02-02/02-14  
(Jan 21 not Jan 9 — avoids active suppression phase, consistent with operational practice)

### Fix 2 — Composite spatial misregistration
Pre and post composites had ~136m (~7 pixel) origin offset. Fixed by establishing one master
reference grid (first pre-event VV scene) and reprojecting all four composites to it.

### Improvement 1 — Median composite
`nanmean` → `nanmedian` for robustness against single anomalous scenes.

### Improvement 2 — LIA flagging
Buildings with mean LIA > 60° flagged as `geometry_limited` (excluded from validation).
Zero flagged in this study — flat alluvial/coastal terrain. Code is correct for steep-terrain events.

### Improvement 3 — No-signal exclusion from validation
`no_data` and `geometry_limited` excluded from DINS matching denominator.
Prior code mapped `no_data` → "not damaged", silently deflating false negatives.

### Improvement 4 — Threshold calibration
F1-maximising sweep 0.5–10.0 dB in 0.1 dB steps. Optimal: 2.7 dB (Eaton), 3.1 dB (Palisades),
mean 2.9 dB written to config. Per-event thresholds discussed and deferred — marginal F1 gain (<0.005).

### `all_touched=True` decision
Considered for reducing no_data rate. Rejected — not industry standard at 20m resolution,
causes neighbourhood backscatter contamination for small buildings. Documented as limitation in README.

---

## Files Changed This Session

| File | What changed |
|------|-------------|
| `config/pipeline_config.yaml` | Track 64 dates; Eaton swath_coverage_pct 87→100; calibrated threshold 3.0→2.9 dB |
| `src/pipeline/composite.py` | Single master reference grid; nanmean→nanmedian |
| `src/pipeline/buildings.py` | LIA flagging: `find_lia_file`, `flag_geometry_limited`, `geometry_limited` class |
| `src/pipeline/validate.py` | Full rewrite: no_data exclusion, `calibrate_threshold`, `update_config_threshold` |
| `scripts/visualise.py` | New: all 9 figures (damage maps, SAR panels, zoom maps, validation, signal dist) |
| `scripts/search_all_tracks.py` | New: CDSE track search utility |
| `scripts/check_track64_coverage.py` | New: verified Track 64/71 footprints |
| `README.md` | New: comprehensive portfolio README with methodology, results, all figures |

---

## Running the Pipeline from Scratch

If any stage needs to be re-run (unlikely — all outputs are on disk):

```bash
# Data already downloaded and processed — skip this unless starting fresh
python -m scripts.run_processing

python -m src.pipeline.composite
python -m src.pipeline.change
python -m src.pipeline.buildings      # ~15-20 min (3.5 GB building footprint load)
python -m src.pipeline.validate       # writes calibrated threshold to config
# If validate changed the threshold, re-run buildings then validate once more:
# del data/vectors/building_damage_*.geojson
# python -m src.pipeline.buildings
# python -m src.pipeline.validate
python -m scripts.visualise
```

---

## Dependencies

```
pyroSAR==0.36.2
rasterio / geopandas / rasterstats / numpy / scipy / shapely
boto3 / matplotlib / contextily / python-dotenv / pyyaml
gdal==3.12.2 (installed via wheel)
```

Never commit `data/` directories. `.env` holds CDSE and AWS credentials.
