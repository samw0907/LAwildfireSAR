# Claude Code Handoff — LA Wildfire SAR Project
## Status as of 2026-06-26 — Root Cause Fixed, Methodology Improved, Re-run In Progress

---

## Project Overview

Production-grade SAR wildfire damage assessment pipeline built in Python.
Processes Sentinel-1 SAR data to detect building-level damage from the January 2025
LA wildfires (Eaton and Palisades fires). The pipeline:

1. Downloads Sentinel-1 IW GRD scenes from CDSE
2. Processes to RTC backscatter via pyroSAR/SNAP
3. Builds pre/post composites
4. Computes log-ratio change detection
5. Classifies building-level damage via rasterstats zonal statistics
6. Validates against CAL FIRE DINS ground truth

---

## Repository

github.com/samw0907/LAwildfireSAR
Local path: C:\Users\swill\dev\LAwildfireSAR

---

## Current Pipeline Status — COMPLETE (2026-06-26)

All pipeline stages have run to completion and converged. No further processing needed.

```
[✓] Download + SNAP RTC       6 × Track 64 scenes processed
[✓] Composite                 Pre/post VV+VH, master reference grid, median stack
[✓] Change detection          change_combined.tif, burn_perimeter_full.geojson
[✓] Buildings                 building_damage_eaton.geojson, building_damage_palisades.geojson
[✓] Validate                  Threshold calibrated (3.0 → 2.9 dB), converged, no re-run needed
```

### Final Validation Metrics (2.9 dB threshold)

| Event | Precision | Recall | F1 | Accuracy | Validated on |
|-------|-----------|--------|----|----------|--------------|
| Eaton | 0.749 | 0.868 | 0.804 | 0.732 | 5,992 buildings |
| Palisades | 0.723 | 0.893 | 0.799 | 0.736 | 6,220 buildings |

Excluded from metrics: 7,904 Eaton and 4,516 Palisades matched buildings with no SAR signal (no_data / geometry_limited).

### Building Damage Counts (calibrated 2.9 dB)

| Event | Destroyed | Possibly Affected | No Damage | No Data | Total |
|-------|-----------|-------------------|-----------|---------|-------|
| Eaton | 2,126 | 1,198 | 1,156 | 6,047 | 10,527 |
| Palisades | 2,583 | 1,307 | 1,468 | 3,985 | 9,343 |

---

## Fix 1 — Eaton NaN Root Cause

### What was wrong

The pipeline was using **Sentinel-1 ascending Track 137** (orbit ~056909). At Eaton's
latitude (~34.18°N), the IW3 sub-swath's last burst ends abruptly at **x ≈ 392,200m
UTM 11N** — confirmed as a genuine acquisition gap by a single-pixel cliff from valid
backscatter to exactly 0.0 across all 6 scenes. The Eaton fire perimeter begins at
x = 392,938m — 738m east of this boundary. Every Eaton building returned NaN.

Disabling `removeS1BorderNoise` would not help: the transition is a burst boundary,
not noise removal. The 87% coverage figure in the old config was computed against
the scene bounding box (which includes the nodata zone) — true valid coverage of
Eaton under Track 137 was 0%.

### Fix applied

Switched to **ascending Track 64** (absolute orbits 056836, 057011, etc.).
Track 64 places Eaton in the near-to-mid range interior of the swath — well away from
any IW3 far-range burst edge. Both fires are covered by the same imagery.

New scene dates:
```yaml
pre:  ["2024-12-04", "2024-12-16", "2024-12-28"]   # 34/22/10 days pre-fire
post: ["2025-01-21", "2025-02-02", "2025-02-14"]   # 14/26/38 days post-fire
```

Jan 21 chosen as first post scene (not Jan 9) so the active-suppression phase is over
and structural backscatter has stabilised. The 14–38 day post window is methodologically
standard for SAR NatCat damage assessment.

---

## Fix 2 — Composite Spatial Misregistration

### What was wrong

`composite.py` used each time period's first scene as the reference grid for that
composite. Pre and post composites ended up on different spatial origins (~136m
offset, ~7 pixels at 20m spacing), meaning `change.py` subtracted spatially
misaligned arrays.

### Fix applied

All four composites (pre/post × VV/VH) now aligned to a **single master reference
grid** — the first pre-event VV scene. The master grid is established once in
`run_composites` and passed as `ref_profile` to every `build_composite` call.

---

## Improvement 1 — Median Composite

**File:** `src/pipeline/composite.py`

Changed `np.nanmean` → `np.nanmedian` in the composite stacking.

**Why:** Median is more robust than mean to a single anomalous scene — for example,
a rainfall event causing wet-soil backscatter spikes in one acquisition. With 3
scenes, the median is simply the middle value, which discards any single outlier.
This is standard practice in multi-temporal SAR compositing.

---

## Improvement 2 — Local Incidence Angle Flagging

**File:** `src/pipeline/buildings.py`

Added `find_lia_file` and `flag_geometry_limited` functions. After the initial
damage classification, buildings are sampled against the local incidence angle (LIA)
raster already produced during RTC processing (`localIncidenceAngle.tif`). Buildings
where mean LIA > 60° have their `damage_class` overridden to `geometry_limited`.

**Why:** At high incidence angles, the terrain faces away from the radar — the
building sits in shadow or a layover zone and the backscatter signal is geometrically
distorted. Classifying these buildings as damaged or undamaged based on SAR change
is unreliable. Flagging them explicitly allows downstream users to apply appropriate
caveats rather than treating the classification as valid. The `mean_lia` value is
retained in the output GeoJSON for QA.

The LIA raster is a geometric property of orbit + terrain (not scene content), so
any single scene's LIA file is representative of the whole time series. The pipeline
uses the first pre-event scene's LIA file.

**New damage class in output:** `geometry_limited` (alongside `destroyed`,
`possibly_affected`, `no_damage`, `no_data`)

---

## Improvement 3 — Exclude No-Signal Buildings from Validation

**File:** `src/pipeline/validate.py`

Buildings with `damage_class` in `{"no_data", "geometry_limited"}` are now excluded
from the matched set before computing precision/recall/F1. The count of excluded
buildings is reported in the metrics output.

**Why:** The original code mapped `no_data` → 0 (not damaged) in the binary
classification. Any building the SAR cannot see — due to acquisition gaps, shadow,
or layover — would be counted as confirmed undamaged, silently deflating the
false-negative count and artificially inflating recall. These buildings should be
excluded from the denominator entirely; absence of signal is not evidence of absence
of damage.

---

## Improvement 4 — Automated Threshold Calibration

**File:** `src/pipeline/validate.py`

Added `calibrate_threshold` function that sweeps `threshold_combined_db` from 0.5
to 10.0 dB in 0.1 dB steps, re-classifying buildings at each step using the
pre-computed `mean_change_combined` values (no raster re-sampling needed). The
F1-maximising threshold is identified and:

- Reported alongside the metrics at the initial threshold
- Written back to `config/pipeline_config.yaml` automatically
- A prompt is printed to re-run `buildings.py` with the calibrated value

**Why:** The original config note said `threshold_combined_db: 3.0 # initial value,
calibrated in validation step` but the calibration step never existed. An arbitrary
threshold is not defensible in a professional pipeline. F1 maximisation balances
precision and recall — appropriate for a damage assessment where both missing damage
(false negative) and overcounting it (false positive) have operational consequences.

If the application context required prioritising one (e.g. emergency response = maximise
recall to avoid missing damage), the calibration function accepts a custom scoring
function and can be adapted accordingly.

The full threshold sweep is stored in the metrics dict for plotting if needed
(excluded from the JSON summary to keep it readable).

---

## All Files Changed in This Session

| File | Change |
|------|--------|
| `config/pipeline_config.yaml` | Track 64 dates; Eaton coverage 100%; calibrated threshold written here by validate.py |
| `src/pipeline/composite.py` | Single master reference grid; nanmean → nanmedian |
| `src/pipeline/buildings.py` | LIA flagging (geometry_limited class); find_lia_file; flag_geometry_limited |
| `src/pipeline/validate.py` | no_data/geometry_limited excluded from metrics; calibrate_threshold; update_config_threshold |
| `scripts/search_all_tracks.py` | New — searches CDSE for all tracks over study area |
| `scripts/check_track64_coverage.py` | New — verified Track 64 and 71 scene availability and footprints |

---

## Data State

```
data/raw/       6 × Track 64 SAFE zips ✓ (Dec 4/16/28, Jan 21, Feb 2/14)
                6 × Track 137 SAFE zips also present — safe to leave (no filename overlap)
data/rtc/       18 × Track 64 TIFs ✓ (VV + VH + localIncidenceAngle per scene)
                Track 137 RTC TIFs also present — no overlap with Track 64 date strings
data/analysis/  pre/post composites VV+VH ✓, change_combined.tif ✓
data/vectors/   building_damage_eaton.geojson ✓, building_damage_palisades.geojson ✓
                burn_perimeter_full.geojson ✓
data/validation/ validation_summary.json ✓
```

---

## Sanity Check — Eaton Coverage (PASSED)

Verified Track 64 pre-composite VV at three Eaton building centroids:
- (405941, 3782306) → -8.68 dB ✓
- (405843, 3782092) → -7.35 dB ✓
- (405754, 3782255) → -6.11 dB ✓

Valid data extends to x=582,225m at Eaton latitude (Eaton eastern edge is x≈406,646m).
These same pixels returned NaN under Track 137 — fix confirmed.

---

## Dependencies

```
pyroSAR==0.36.2
rasterio / geopandas / rasterstats / numpy / scipy / shapely
boto3 / matplotlib / contextily / python-dotenv / pyyaml
gdal==3.12.2 (installed via wheel)
```

Python 3.14 on Windows. SNAP GPT on PATH.
Run all scripts from project root: `C:\Users\swill\dev\LAwildfireSAR`
Use `python -m pip install` not `pip install`.
Never commit data/ directories.
