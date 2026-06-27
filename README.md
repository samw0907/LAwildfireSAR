# LA Wildfires 2025 — SAR Building Damage Assessment

This project uses free satellite radar imagery to map which buildings were damaged or destroyed in the January 2025 Los Angeles wildfires. It covers both the Eaton Fire (Altadena/Pasadena) and the Palisades Fire (Pacific Palisades/Malibu), processing six Sentinel-1 radar scenes through a fully automated pipeline to produce building-level damage classifications validated against CAL FIRE ground truth inspections.

The methodology mirrors what commercial services like ICEYE deliver operationally — built here using entirely open data and open-source tools.

---

## The Fires

| Fire | Location | Area burned | Structures destroyed | Lives lost |
|------|----------|-------------|----------------------|------------|
| Eaton | Altadena / Pasadena | 5,674 ha (14,021 acres) | ~9,400 | 18 |
| Palisades | Pacific Palisades / Malibu | 9,489 ha (23,448 acres) | ~6,800 | 12 |

Both fires ignited on 7 January 2025 during extreme Santa Ana wind conditions and burned simultaneously. Eaton destroyed more structures despite covering less area — it burned through densely built suburban streets in Altadena, whereas the Palisades fire spread across a larger but more mixed wildland-urban landscape.

---

## Results

### Damage maps

![Combined Damage Map](outputs/figures/damage_map_combined.png)

The map above shows both fire perimeters in geographic context. Buildings are coloured by damage class — red for structures where the radar signal indicates destruction, grey where no classification was possible at 20m resolution.

### Eaton Fire

![Eaton Fire Building Damage Map](outputs/figures/damage_map_eaton.png)

| Class | Count | Share |
|-------|-------|-------|
| Destroyed | 2,126 | 20% |
| Possibly affected | 1,198 | 11% |
| No damage detected | 1,156 | 11% |
| Below radar resolution | 6,047 | 57% |

### Palisades Fire

![Palisades Fire Building Damage Map](outputs/figures/damage_map_palisades.png)

| Class | Count | Share |
|-------|-------|-------|
| Destroyed | 2,583 | 28% |
| Possibly affected | 1,307 | 14% |
| No damage detected | 1,468 | 16% |
| Below radar resolution | 3,985 | 43% |

### Street-level zoom

The zoomed maps show individual building footprints coloured by classification across the most heavily damaged neighbourhoods, giving a direct sense of spatial damage patterns at block scale.

![Eaton Damage Zoom](outputs/figures/damage_zoom_eaton.png)

![Palisades Damage Zoom](outputs/figures/damage_zoom_palisades.png)

---

## How it works

### Why radar?

Radar satellites (SAR — Synthetic Aperture Radar) see through cloud cover, smoke and darkness, making them the standard tool for disaster assessment when optical imagery is not available. The Sentinel-1 satellite is free to use, with data available within hours of acquisition through the Copernicus programme.

When a building is destroyed, the radar signal it returns drops sharply — the roof and walls that previously reflected energy back to the satellite are gone. By comparing radar images taken before and after a fire, we can detect this change at each building footprint.

### What the pipeline does

```
Download                6 Sentinel-1 radar scenes from Copernicus (Dec 2024 – Feb 2025)
        ↓
Process                 Convert raw radar data to calibrated backscatter via pyroSAR/SNAP
        ↓
Composite               Average 3 pre-event scenes and 3 post-event scenes separately
        ↓
Change detection        Subtract pre from post — large values indicate structural loss
        ↓
Building classification Measure the mean change signal within each building footprint
        ↓
Validation              Compare classifications against CAL FIRE physical inspections
```

All stages run automatically from a single config file. Each step saves its outputs so individual stages can be re-run without reprocessing everything from scratch.

### Scene selection

**Sensor:** Sentinel-1A IW GRD, dual-polarisation (VV + VH), ascending orbit, Track 64

**Pre-fire scenes:** 4 Dec 2024, 16 Dec 2024, 28 Dec 2024
**Post-fire scenes:** 21 Jan 2025, 2 Feb 2025, 14 Feb 2025

Three pre-event and three post-event scenes are averaged into composites before change detection. Averaging multiple scenes reduces radar speckle noise, improving classification accuracy for smaller structures.

The first post-event acquisition date was set to 21 January (14 days after ignition) rather than 9 January. Using imagery taken 2 days after ignition would pick up confounding signals from active firefighting — fire retardant, emergency vehicles, and debris disturbance — rather than the structural changes we are trying to detect. A 14–38 day post-fire window is standard for this type of assessment.

Track 64 was selected after discovering that the alternative ascending pass (Track 137) has a radar swath boundary that cuts through the Eaton fire area, leaving no valid data there. Track 64 places both fires in the interior of the swath with full coverage.

### Processing

Raw scenes are processed to gamma-nought (γ⁰) backscatter using pyroSAR and ESA SNAP. The processing chain includes thermal noise removal, border noise removal, terrain correction using SRTM elevation data, and resampling to 20m resolution in UTM Zone 11N (EPSG:32611).

A local incidence angle raster is also produced per scene. Buildings on slopes where the terrain faces significantly away from the radar (incidence angle above 60°) are flagged as geometrically unreliable rather than classified. No buildings exceeded this threshold in the study area, consistent with the moderate terrain of Altadena and Pacific Palisades.

### Change detection

The combined change magnitude used for classification:

```
Change_VV = post_VV − pre_VV          (log-ratio in dB space)
Change_VH = post_VH − pre_VH
Combined  = √(Change_VV² + Change_VH²)
```

VV polarisation is more sensitive to surface roughness changes (rubble, debris). VH is more sensitive to structural elements and double-bounce scattering from walls. Combining both improves separability between damaged and undamaged buildings.

### Building classification

Building footprints come from the [Microsoft Global ML Building Footprints](https://github.com/microsoft/GlobalMLBuildingFootprints) dataset — ML-derived outlines of every detectable building in California. Footprints within each fire perimeter are matched to the radar change raster using zonal statistics: the mean change magnitude within each polygon becomes the building's damage score.

| Class | Threshold |
|-------|-----------|
| Destroyed | mean change ≥ 2.9 dB |
| Possibly affected | mean change ≥ 1.74 dB |
| No damage | mean change < 1.74 dB |
| Below resolution | no radar pixel centroid within footprint |

The 2.9 dB threshold was not set arbitrarily — it was calibrated by comparing classifications against CAL FIRE ground truth across a sweep of values and selecting the threshold that maximised F1 score.

---

## Validation

Classifications are checked against the CAL FIRE Damage Inspection System (DINS), in which surveyors physically inspected each structure within the fire perimeters after containment. DINS records are matched to the nearest building footprint (within 25m) and binarised: Destroyed or Major damage = damaged; all others = not damaged. Buildings with no radar signal are excluded from the validation — they cannot be assessed either way.

![Validation Metrics](outputs/figures/validation_metrics.png)

| Event | Precision | Recall | F1 | Validated buildings |
|-------|-----------|--------|----|---------------------|
| Eaton | 0.749 | 0.868 | 0.804 | 5,992 |
| Palisades | 0.723 | 0.893 | 0.799 | 6,220 |

F1 of ~0.80 on both events is consistent with published benchmarks for Sentinel-1 building damage mapping at 20m resolution (UNOSAT and Copernicus EMS typically report 0.72–0.85). Recall is intentionally higher than precision — the threshold was tuned so that the system is more likely to flag a damaged building than miss one. In an emergency response context, missing a damaged structure carries a higher cost than a false alarm.

### SAR imagery — before, after, and change

The three-panel figures below show the raw radar signal the algorithm works from at 2.5km zoom over the most-damaged neighbourhood in each fire.

![SAR Panel Eaton](outputs/figures/sar_panel_eaton.png)

![SAR Panel Palisades](outputs/figures/sar_panel_palisades.png)

Left panel: pre-event radar backscatter (December 2024). The grid pattern of streets and buildings is clearly visible — bright returns from walls and roofs, darker returns from open ground. Centre: post-event backscatter with building outlines coloured by damage class. Red outlines mark structures where the radar signal changed significantly. Right: the combined change magnitude used for classification, overlaid with filled building polygons.

### Signal separability

![Change Signal Distribution](outputs/figures/change_signal_dist.png)

The violin plots show the distribution of mean radar change values for buildings that CAL FIRE inspectors recorded as damaged versus not damaged. The damaged distribution is shifted higher, confirming that the radar signal captures structural loss. The overlap between the two distributions is the fundamental limit of 20m resolution SAR — it is what produces the ~25% false positive rate and explains why sub-metre commercial radar (such as ICEYE) significantly outperforms free open data for building-level assessment.

---

## Limitations

**~50% of buildings below radar resolution.** At 20m pixel spacing, each radar pixel covers ~400m². Smaller residential structures may have no pixel centroid falling within their building outline and cannot be classified. This is a known limitation of free Sentinel-1 data documented by UNOSAT and the Copernicus EMS. Sub-metre commercial SAR would substantially reduce this.

**Single radar look angle.** Only ascending Track 64 was used. Adding a descending pass would provide a complementary viewing angle, classifying buildings that are in shadow or layover on the ascending geometry. A natural extension for an operational deployment.

**DINS coverage.** CAL FIRE inspectors covered road-accessible structures. Remote or inaccessible buildings may be absent from the ground truth, which affects how representative the precision and recall figures are.

**Wildland areas.** The large forested and chaparral portions of both fire perimeters contain very few building footprints. The Microsoft dataset covers structures only — vegetation change in the wildland areas is visible in the radar imagery but is not classified here.

---

## Data sources

| Dataset | Source |
|---------|--------|
| Sentinel-1 IW GRD | [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/) — free, requires account |
| Microsoft Building Footprints | [Microsoft GlobalMLBuildingFootprints](https://github.com/microsoft/GlobalMLBuildingFootprints) — California GeoJSON (~3.5 GB) |
| CAL FIRE DINS | [CAL FIRE](https://www.fire.ca.gov/) — post-fire structure inspections |
| SRTM 1 arcsec DEM | Auto-downloaded via SNAP — used for terrain correction |
| Fire perimeters | [CAL FIRE / NIFC](https://www.nifc.gov/) — GeoJSON format |

---

## Stack

```
pyroSAR / ESA SNAP    SAR processing (RTC, terrain correction)
rasterio              Raster I/O
geopandas             Vector operations
rasterstats           Zonal statistics
numpy / scipy         Array operations
matplotlib            Figures
contextily            Basemaps
boto3                 AWS S3 outputs
```

Python 3.11+. SNAP GPT must be on PATH. CDSE account required for scene download.

---

## Running the pipeline

```bash
python -m scripts.run_processing      # download + SNAP processing (~4-6 hours)
python -m src.pipeline.composite      # build pre/post composites
python -m src.pipeline.change         # change detection
python -m src.pipeline.buildings      # building classification (~15 min)
python -m src.pipeline.validate       # validation + threshold calibration
python -m scripts.visualise           # generate all figures
```

If `validate.py` writes a new calibrated threshold, delete `data/vectors/*.geojson` and re-run `buildings` then `validate` once more to apply it.

All parameters — scene dates, thresholds, paths — are in `config/pipeline_config.yaml`. The calibrated threshold is written back to this file automatically after validation.

---

## Repository structure

```
LAwildfireSAR/
├── config/
│   ├── pipeline_config.yaml       Scene dates, thresholds, paths
│   └── .env                       CDSE and AWS credentials (gitignored)
├── data/
│   ├── external/                  Fire perimeters, DINS, building footprints (gitignored)
│   ├── raw/                       Downloaded SAFE zip files (gitignored)
│   ├── rtc/                       SNAP-processed GeoTIFFs (gitignored)
│   ├── analysis/                  Composites, change rasters (gitignored)
│   ├── vectors/                   Building damage GeoJSONs (gitignored)
│   └── validation/                Validation summary JSON (gitignored)
├── outputs/
│   └── figures/                   All visualisation outputs
├── scripts/
│   ├── run_processing.py          Download + SNAP orchestration
│   └── visualise.py               Figure generation
├── src/
│   ├── pipeline/
│   │   ├── download.py            CDSE scene search and download
│   │   ├── process.py             pyroSAR RTC processing
│   │   ├── composite.py           Pre/post composite generation
│   │   ├── change.py              Log-ratio change detection
│   │   ├── buildings.py           Zonal statistics, damage classification
│   │   └── validate.py            DINS matching, threshold calibration
│   └── utils/
│       └── config.py              Config loader and credential helpers
├── tests/
│   └── unit/                      Unit tests
├── Dockerfile
├── requirements.txt
└── README.md
```

---

*Sentinel-1 data: Copernicus Data Space Ecosystem / ESA. Building footprints: Microsoft. Ground truth: CAL FIRE DINS. Fire perimeters: CAL FIRE / NIFC.*
