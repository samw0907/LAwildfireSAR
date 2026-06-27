# scripts/validate_config.py
# Validates pipeline_config.yaml schema and required fields.
# Run before executing the pipeline to catch config errors early.

from src.utils.config import load_config

REQUIRED_KEYS = {
    "study_area": ["name", "combined_bbox", "events"],
    "scenes": ["pre", "post", "product_type", "orbit_direction"],
    "processing": ["crs", "spacing", "polarizations", "dem"],
    "change_detection": ["threshold_combined_db"],
    "aws": ["bucket", "prefix", "region"],
    "paths": ["raw_scenes", "rtc_output", "external", "snap_aux"],
}

REQUIRED_EVENTS = ["eaton", "palisades"]
REQUIRED_EVENT_KEYS = ["bbox", "name", "swath_coverage_pct", "coverage_note"]


def validate_config():
    config = load_config()
    errors = []

    for section, keys in REQUIRED_KEYS.items():
        if section not in config:
            errors.append(f"Missing section: {section}")
            continue
        for key in keys:
            if key not in config[section]:
                errors.append(f"Missing key: {section}.{key}")

    for event in REQUIRED_EVENTS:
        if event not in config.get("study_area", {}).get("events", {}):
            errors.append(f"Missing event: study_area.events.{event}")
            continue
        for key in REQUIRED_EVENT_KEYS:
            if key not in config["study_area"]["events"][event]:
                errors.append(f"Missing key: study_area.events.{event}.{key}")

    pre = config.get("scenes", {}).get("pre", [])
    post = config.get("scenes", {}).get("post", [])
    if len(pre) != 3:
        errors.append(f"Expected 3 pre-event scenes, got {len(pre)}")
    if len(post) != 3:
        errors.append(f"Expected 3 post-event scenes, got {len(post)}")

    bbox = config.get("study_area", {}).get("combined_bbox", [])
    if len(bbox) != 4:
        errors.append("combined_bbox must have 4 values [lon_min, lat_min, lon_max, lat_max]")

    if errors:
        print("Config validation FAILED:")
        for e in errors:
            print(f"  - {e}")
        raise SystemExit(1)

    print(f"Config validation passed.")
    print(f"  Study area: {config['study_area']['name']}")
    print(f"  Pre scenes: {config['scenes']['pre']}")
    print(f"  Post scenes: {config['scenes']['post']}")
    print(f"  Orbit direction: {config['scenes']['orbit_direction']}")
    print(f"  Threshold: {config['change_detection']['threshold_combined_db']} dB")


if __name__ == "__main__":
    validate_config()