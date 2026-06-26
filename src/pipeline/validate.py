# src/pipeline/validate.py
import os
import json
import numpy as np
import geopandas as gpd
from src.utils.config import load_config


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
    No_damage and no_data = not damaged.
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


def validate_event(event_name, buildings_gdf, dins_path,
                   target_crs, config, damage_col="damage_cat"):
    """
    Validate pipeline building damage classification against DINS ground truth.
    Spatially joins DINS points to building footprints, computes binary metrics.
    Includes swath coverage metadata in output.
    Returns metrics dict and joined GeoDataFrame for figure generation.
    """
    print(f"\nValidating: {event_name}")

    # Load swath coverage from buildings GDF (set in buildings.py)
    swath_coverage_pct = int(buildings_gdf["swath_coverage_pct"].iloc[0])
    coverage_note = buildings_gdf["coverage_note"].iloc[0]

    if swath_coverage_pct < 100:
        print(f"  WARNING: Partial swath coverage ({swath_coverage_pct}%) — {coverage_note}")
        print(f"  Validation metrics reflect covered area only")

    dins = load_dins(dins_path, target_crs)
    print(f"  DINS records: {len(dins)}")
    print(f"  DINS columns: {list(dins.columns)}")

    joined = gpd.sjoin_nearest(
        dins[["geometry", damage_col]],
        buildings_gdf[["geometry", "damage_class", "mean_change_combined"]],
        how="inner",
        max_distance=25
    )
    print(f"  Matched DINS records to buildings: {len(joined)}")

    if len(joined) == 0:
        print(f"  WARNING: No DINS records matched to buildings for {event_name}")
        return None, None

    y_true = get_dins_damage_binary(joined, damage_col).values
    y_pred = get_pipeline_damage_binary(joined).values

    metrics = compute_metrics(y_true, y_pred)
    metrics["event"] = event_name
    metrics["dins_records"] = len(dins)
    metrics["matched_records"] = len(joined)
    metrics["swath_coverage_pct"] = swath_coverage_pct
    metrics["coverage_note"] = coverage_note

    if swath_coverage_pct < 100:
        metrics["coverage_warning"] = (
            f"Metrics reflect {swath_coverage_pct}% of official perimeter only. "
            f"{coverage_note}"
        )

    print(f"  Precision: {metrics['precision']}")
    print(f"  Recall:    {metrics['recall']}")
    print(f"  F1:        {metrics['f1']}")
    print(f"  Accuracy:  {metrics['accuracy']}")

    joined["y_true"] = y_true
    joined["y_pred"] = y_pred
    joined["validation_class"] = joined.apply(
        lambda r: "true_positive" if r.y_true == 1 and r.y_pred == 1
        else "false_positive" if r.y_true == 0 and r.y_pred == 1
        else "false_negative" if r.y_true == 1 and r.y_pred == 0
        else "true_negative",
        axis=1
    )

    return metrics, joined


def run_validation(buildings_results=None, config=None):
    """
    Run validation for all events with available DINS data.
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

    summary_path = os.path.join(validation_dir, "validation_summary.json")
    with open(summary_path, "w") as f:
        json.dump(all_metrics, f, indent=2)
    print(f"\nValidation summary written: {summary_path}")

    return all_metrics, all_joined


if __name__ == "__main__":
    metrics, joined = run_validation()
    for event, m in metrics.items():
        print(f"\n{event}:")
        print(f"  F1: {m['f1']} | Precision: {m['precision']} | Recall: {m['recall']}")
        print(f"  Swath coverage: {m['swath_coverage_pct']}%")
        if "coverage_warning" in m:
            print(f"  {m['coverage_warning']}")