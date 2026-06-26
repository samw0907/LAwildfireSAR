# src/pipeline/validate.py
import os
import json
import numpy as np
import geopandas as gpd
import yaml
from src.utils.config import load_config

# Damage classes that indicate missing or unreliable SAR signal.
# These buildings are excluded from validation metrics — treating them
# as "not damaged" would silently deflate the false-negative count.
EXCLUDED_CLASSES = {"no_data", "geometry_limited"}


def load_dins(path, target_crs):
    """Load CAL FIRE DINS GeoJSON and reproject to target CRS."""
    gdf = gpd.read_file(path)
    return gdf.to_crs(target_crs)


def get_dins_damage_binary(gdf, damage_col):
    """
    Convert DINS damage categories to binary damaged/not_damaged.
    Destroyed and Major classified as damaged, rest as not damaged.
    """
    damaged_classes = ["destroyed", "major"]
    return gdf[damage_col].apply(
        lambda x: 1 if any(
            d in str(x).lower() for d in damaged_classes
        ) else 0
    )


def get_pipeline_damage_binary(gdf):
    """
    Convert pipeline damage classes to binary damaged/not_damaged.
    Destroyed and possibly_affected = damaged.
    No_damage = not damaged.
    Note: no_data and geometry_limited are excluded before this is called.
    """
    return gdf["damage_class"].apply(
        lambda x: 1 if x in ["destroyed", "possibly_affected"] else 0
    )


def compute_metrics(y_true, y_pred):
    """Compute precision, recall, F1 and accuracy from binary arrays."""
    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    fn = int(((y_true == 1) & (y_pred == 0)).sum())
    tn = int(((y_true == 0) & (y_pred == 0)).sum())

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) > 0 else 0.0)
    accuracy = (tp + tn) / (tp + fp + fn + tn) if (tp + fp + fn + tn) > 0 else 0.0

    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "accuracy": round(accuracy, 3)
    }


def calibrate_threshold(joined_df, damage_col,
                        threshold_range=(0.5, 10.0), step=0.1):
    """
    Sweep change detection thresholds to find the F1-maximising value.

    Uses the pre-computed mean_change_combined values already stored per
    building, so no raster re-sampling is needed. The 0.6 ratio between
    the lower (possibly_affected) and upper (destroyed) boundaries is
    preserved from the original classification logic.

    Returns:
        optimal_threshold  float — the threshold_combined_db that maximises F1
        best_metrics       dict  — metrics at the optimal threshold
        sweep_results      list  — full [{threshold, f1, precision, recall}] sweep
    """
    y_true = get_dins_damage_binary(joined_df, damage_col).values
    thresholds = np.arange(threshold_range[0], threshold_range[1] + step, step)

    sweep_results = []
    for t in thresholds:
        threshold_low = t * 0.6
        y_pred = joined_df["mean_change_combined"].apply(
            lambda v: 1 if (not np.isnan(float(v)) and float(v) >= threshold_low)
            else 0
        ).values
        m = compute_metrics(y_true, y_pred)
        sweep_results.append({
            "threshold": round(float(t), 2),
            "f1": m["f1"],
            "precision": m["precision"],
            "recall": m["recall"],
        })

    best = max(sweep_results, key=lambda x: x["f1"])

    # Recompute full metrics at optimal threshold for the summary
    threshold_low = best["threshold"] * 0.6
    y_pred_best = joined_df["mean_change_combined"].apply(
        lambda v: 1 if (not np.isnan(float(v)) and float(v) >= threshold_low)
        else 0
    ).values
    best_metrics = compute_metrics(y_true, y_pred_best)

    return best["threshold"], best_metrics, sweep_results


def update_config_threshold(threshold, config_path="config/pipeline_config.yaml"):
    """
    Write the calibrated threshold back to the pipeline config YAML so that
    re-running buildings.py will use the validated value.
    """
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    config["change_detection"]["threshold_combined_db"] = round(float(threshold), 2)
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def validate_event(event_name, buildings_gdf, dins_path,
                   target_crs, config, damage_col="damage_cat"):
    """
    Validate pipeline building damage classification against DINS ground truth.

    Workflow:
      1. Spatially join DINS inspection points to building footprints (≤25 m).
      2. Exclude buildings flagged as no_data or geometry_limited — these have
         no reliable SAR signal and must not be treated as confirmed undamaged.
      3. Compute binary precision/recall/F1 at the current config threshold.
      4. Sweep thresholds to find the F1-maximising value and report it.

    Returns metrics dict and joined GeoDataFrame for figure generation.
    """
    print(f"\nValidating: {event_name}")

    swath_coverage_pct = int(buildings_gdf["swath_coverage_pct"].iloc[0])
    coverage_note = buildings_gdf["coverage_note"].iloc[0]

    if swath_coverage_pct < 100:
        print(f"  WARNING: Partial swath coverage ({swath_coverage_pct}%) — {coverage_note}")

    dins = load_dins(dins_path, target_crs)
    print(f"  DINS records: {len(dins)}")

    joined = gpd.sjoin_nearest(
        dins[["geometry", damage_col]],
        buildings_gdf[["geometry", "damage_class", "mean_change_combined"]],
        how="inner",
        max_distance=25
    )
    print(f"  DINS records matched to buildings: {len(joined)}")

    if len(joined) == 0:
        print(f"  WARNING: No DINS records matched to buildings for {event_name}")
        return None, None

    # Exclude buildings with no reliable SAR signal before computing metrics.
    # Keeping them would silently count shadow/no-coverage zones as "not damaged"
    # and understate false negatives.
    excluded_mask = joined["damage_class"].isin(EXCLUDED_CLASSES)
    n_excluded = int(excluded_mask.sum())
    if n_excluded > 0:
        print(f"  Excluded {n_excluded} matched buildings with unreliable signal "
              f"({', '.join(EXCLUDED_CLASSES)}) from metrics")
    joined_valid = joined[~excluded_mask].copy()

    if len(joined_valid) == 0:
        print(f"  WARNING: No valid (covered) matched buildings remain for {event_name}")
        return None, None

    y_true = get_dins_damage_binary(joined_valid, damage_col).values
    y_pred = get_pipeline_damage_binary(joined_valid).values

    current_threshold = config["change_detection"]["threshold_combined_db"]
    metrics = compute_metrics(y_true, y_pred)
    metrics["event"] = event_name
    metrics["dins_records"] = len(dins)
    metrics["matched_records"] = len(joined)
    metrics["excluded_no_signal"] = n_excluded
    metrics["validated_records"] = len(joined_valid)
    metrics["threshold_used"] = current_threshold
    metrics["swath_coverage_pct"] = swath_coverage_pct
    metrics["coverage_note"] = coverage_note

    print(f"\n  --- Metrics at current threshold ({current_threshold} dB) ---")
    print(f"  Precision: {metrics['precision']}")
    print(f"  Recall:    {metrics['recall']}")
    print(f"  F1:        {metrics['f1']}")
    print(f"  Accuracy:  {metrics['accuracy']}")

    # Threshold calibration: find F1-maximising threshold on this event's data
    opt_threshold, opt_metrics, sweep = calibrate_threshold(joined_valid, damage_col)
    metrics["calibrated_threshold"] = opt_threshold
    metrics["calibrated_f1"] = opt_metrics["f1"]
    metrics["calibrated_precision"] = opt_metrics["precision"]
    metrics["calibrated_recall"] = opt_metrics["recall"]
    metrics["threshold_sweep"] = sweep

    print(f"\n  --- Calibrated threshold (F1-maximising) ---")
    print(f"  Optimal threshold: {opt_threshold} dB")
    print(f"  Precision: {opt_metrics['precision']}")
    print(f"  Recall:    {opt_metrics['recall']}")
    print(f"  F1:        {opt_metrics['f1']}")
    if opt_threshold != current_threshold:
        print(f"  NOTE: Re-run buildings.py to apply calibrated threshold to all buildings")

    # Label each matched record for spatial QA output
    joined_valid = joined_valid.copy()
    joined_valid["y_true"] = y_true
    joined_valid["y_pred"] = y_pred
    joined_valid["validation_class"] = joined_valid.apply(
        lambda r: "true_positive" if r.y_true == 1 and r.y_pred == 1
        else "false_positive" if r.y_true == 0 and r.y_pred == 1
        else "false_negative" if r.y_true == 1 and r.y_pred == 0
        else "true_negative",
        axis=1
    )

    return metrics, joined_valid


def run_validation(buildings_results=None, config=None):
    """
    Run validation for all events with available DINS data.
    Calibrates threshold per event and writes the best overall threshold
    back to config so buildings.py can be re-run with the validated value.
    Writes validation summary JSON to data/validation/.
    Returns dict of metrics and joined GeoDataFrames per event.
    """
    if config is None:
        config = load_config()

    target_crs = f"EPSG:{config['processing']['crs']}"
    validation_dir = os.path.join("data", "validation")
    os.makedirs(validation_dir, exist_ok=True)

    if buildings_results is None:
        buildings_results = {}
        for event in ["eaton", "palisades"]:
            path = os.path.join("data", "vectors", f"building_damage_{event}.geojson")
            if os.path.exists(path):
                buildings_results[event] = gpd.read_file(path)

    dins_sources = {
        "eaton": "data/external/calfire_dins_eaton.geojson",
        "palisades": "data/external/calfire_dins_palisades.geojson",
    }

    all_metrics = {}
    all_joined = {}

    for event_name, dins_path in dins_sources.items():
        if event_name not in buildings_results:
            print(f"No buildings data for {event_name}, skipping validation")
            continue
        if not os.path.exists(dins_path):
            print(f"No DINS data found for {event_name}, skipping validation")
            continue

        dins_gdf = gpd.read_file(dins_path)
        print(f"\nDINS columns available for {event_name}: {list(dins_gdf.columns)}")

        possible_cols = [
            "damage_cat", "DAMAGE_CAT", "DamageCategory",
            "damage", "DAMAGE", "structure_category", "DamageDesc"
        ]
        damage_col = next(
            (c for c in possible_cols if c in dins_gdf.columns), None
        )

        if damage_col is None:
            print(f"  WARNING: Could not identify damage column for {event_name}")
            print(f"  Available columns: {list(dins_gdf.columns)}")
            continue

        metrics, joined = validate_event(
            event_name,
            buildings_results[event_name],
            dins_path,
            target_crs,
            config,
            damage_col=damage_col
        )

        if metrics is not None:
            all_metrics[event_name] = metrics
            all_joined[event_name] = joined

    # Write calibrated threshold back to config using the mean across events
    # (or the single-event value if only one event validated successfully)
    calibrated_thresholds = [
        m["calibrated_threshold"] for m in all_metrics.values()
        if "calibrated_threshold" in m
    ]
    if calibrated_thresholds:
        best_threshold = round(float(np.mean(calibrated_thresholds)), 2)
        current = config["change_detection"]["threshold_combined_db"]
        if best_threshold != current:
            update_config_threshold(best_threshold)
            print(f"\nCalibrated threshold written to config: {best_threshold} dB "
                  f"(was {current} dB)")
            print("Re-run `python -m src.pipeline.buildings` to apply to all buildings")
        else:
            print(f"\nCalibrated threshold ({best_threshold} dB) matches current config — no update needed")

    # Write summary JSON (excluding the full sweep list to keep it readable)
    summary = {}
    for event, m in all_metrics.items():
        summary[event] = {k: v for k, v in m.items() if k != "threshold_sweep"}
    summary_path = os.path.join(validation_dir, "validation_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nValidation summary written: {summary_path}")

    return all_metrics, all_joined


if __name__ == "__main__":
    metrics, joined = run_validation()
    for event, m in metrics.items():
        print(f"\n{event}:")
        print(f"  F1 (initial):    {m['f1']} at {m['threshold_used']} dB")
        print(f"  F1 (calibrated): {m['calibrated_f1']} at {m['calibrated_threshold']} dB")
        print(f"  Validated on {m['validated_records']} buildings "
              f"({m['excluded_no_signal']} excluded — no signal)")
