# src/pipeline/buildings.py
import os
import numpy as np
import rasterio
import geopandas as gpd
from shapely.geometry import box
from src.utils.config import load_config
from rasterstats import zonal_stats


def load_perimeter(path, target_crs):
    """Load a fire perimeter GeoJSON and reproject to target CRS."""
    gdf = gpd.read_file(path)
    return gdf.to_crs(target_crs)


def load_buildings_clipped(buildings_path, clip_geom, target_crs):
    """
    Load Microsoft Building Footprints clipped to clip_geom bounding box.
    Converts bbox to WGS84 for reading since California.geojson is in EPSG:4326.
    Returns GeoDataFrame in target CRS.
    """
    print("  Loading building footprints (this may take a few minutes)...")

    clip_gdf = gpd.GeoDataFrame(geometry=[clip_geom], crs=target_crs)
    clip_wgs84 = clip_gdf.to_crs("EPSG:4326")
    bounds = clip_wgs84.total_bounds

    gdf = gpd.read_file(
        buildings_path,
        bbox=(bounds[0], bounds[1], bounds[2], bounds[3])
    )
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    return gdf.to_crs(target_crs)


def extract_mean_change(buildings_gdf, change_raster_path):
    """
    Extract mean backscatter change value per building footprint polygon
    using rasterstats zonal statistics. Vectorised across all buildings
    in a single pass — standard approach for operational geospatial pipelines.
    Returns buildings GeoDataFrame with mean_change_combined column added.
    """
    print(f"  Running zonal statistics across {len(buildings_gdf)} buildings...")

    with rasterio.open(change_raster_path) as src:
        raster_crs = src.crs

    buildings_reproj = buildings_gdf.to_crs(raster_crs)

    stats = zonal_stats(
        buildings_reproj,
        change_raster_path,
        stats=["mean"],
        nodata=np.nan,
        geojson_out=False
    )

    buildings_gdf = buildings_gdf.copy()
    buildings_gdf["mean_change_combined"] = [
        s["mean"] if s["mean"] is not None else np.nan
        for s in stats
    ]

    return buildings_gdf


def classify_damage(buildings_gdf, config):
    """
    Classify buildings into damage categories based on mean change value.
    Classes: destroyed, possibly_affected, no_damage, no_data.
    Thresholds from config.
    """
    threshold_high = config["change_detection"]["threshold_combined_db"]
    threshold_low = threshold_high * 0.6

    def assign_class(val):
        if val is None or np.isnan(val):
            return "no_data"
        elif val >= threshold_high:
            return "destroyed"
        elif val >= threshold_low:
            return "possibly_affected"
        else:
            return "no_damage"

    buildings_gdf = buildings_gdf.copy()
    buildings_gdf["damage_class"] = buildings_gdf["mean_change_combined"].apply(
        assign_class
    )
    return buildings_gdf


def run_buildings(config=None):
    """
    Run building damage classification for both Eaton and Palisades events.
    Loads building footprints once, filters to within perimeters before
    running zonal statistics — correct operational approach.
    Attaches swath coverage metadata per event from config.
    Writes per-event GeoJSON outputs to data/vectors/.
    Returns dict of GeoDataFrames keyed by event name.
    """
    if config is None:
        config = load_config()

    change_raster = os.path.join("data", "analysis", "change_combined.tif")
    vectors_dir = os.path.join("data", "vectors")
    os.makedirs(vectors_dir, exist_ok=True)
    target_crs = f"EPSG:{config['processing']['crs']}"
    buildings_path = os.path.join(
        "data", "external", "California.geojson", "California.geojson"
    )

    events = {
        "eaton": "data/external/eaton_perimeter.geojson",
        "palisades": "data/external/palisades_perimeter.geojson",
    }

    # Check if all outputs already exist
    all_exist = all(
        os.path.exists(os.path.join(vectors_dir, f"building_damage_{e}.geojson"))
        for e in events
    )
    if all_exist:
        print("All building damage outputs already exist, loading from disk...")
        return {
            e: gpd.read_file(os.path.join(vectors_dir, f"building_damage_{e}.geojson"))
            for e in events
        }

    # Load all perimeters
    print("Loading fire perimeters...")
    perimeters = {
        name: load_perimeter(path, target_crs)
        for name, path in events.items()
    }

    # Combined bbox for single building file read
    combined_bounds = gpd.GeoDataFrame(
        geometry=[p.union_all() for p in perimeters.values()],
        crs=target_crs
    ).total_bounds
    combined_bbox = box(*combined_bounds)

    # Load buildings once clipped to combined bbox
    print("Loading building footprints across combined fire extent...")
    all_buildings = load_buildings_clipped(buildings_path, combined_bbox, target_crs)
    print(f"Total buildings in combined bbox: {len(all_buildings)}")

    # Filter to within fire perimeters BEFORE zonal statistics
    print("Filtering buildings to within fire perimeters...")
    combined_perimeter_union = gpd.GeoDataFrame(
        geometry=[p.union_all() for p in perimeters.values()],
        crs=target_crs
    ).union_all()

    all_buildings = all_buildings[
        all_buildings.intersects(combined_perimeter_union)
    ].copy().reset_index(drop=True)
    print(f"Buildings within fire perimeters: {len(all_buildings)}")

    if len(all_buildings) == 0:
        raise RuntimeError(
            "No buildings found within fire perimeters — check CRS and perimeter data"
        )

    # Run zonal statistics on perimeter buildings only
    print("Extracting mean backscatter change per building...")
    all_buildings = extract_mean_change(all_buildings, change_raster)

    # Classify damage
    print("Classifying damage...")
    all_buildings = classify_damage(all_buildings, config)
    all_buildings["area_m2"] = all_buildings.geometry.area

    results = {}

    # Split by perimeter for each event and write outputs
    for event_name, perimeter_gdf in perimeters.items():
        output_path = os.path.join(vectors_dir, f"building_damage_{event_name}.geojson")
        perimeter_union = perimeter_gdf.union_all()

        event_buildings = all_buildings[
            all_buildings.intersects(perimeter_union)
        ].copy()
        event_buildings["event"] = event_name
        event_buildings = event_buildings.reset_index(drop=True)

        # Attach swath coverage metadata from config
        event_config = config["study_area"]["events"][event_name]
        event_buildings["swath_coverage_pct"] = event_config["swath_coverage_pct"]
        event_buildings["coverage_note"] = event_config["coverage_note"]

        print(f"\n{event_name}: {len(event_buildings)} buildings within perimeter")
        print(f"  Swath coverage: {event_config['swath_coverage_pct']}%")
        if event_config["swath_coverage_pct"] < 100:
            print(f"  WARNING: {event_config['coverage_note']}")
        print(event_buildings["damage_class"].value_counts())

        event_buildings.to_file(output_path, driver="GeoJSON")
        print(f"Written: {output_path}")
        results[event_name] = event_buildings

    print("\nBuilding damage classification complete.")
    return results


if __name__ == "__main__":
    results = run_buildings()
    for event, gdf in results.items():
        print(f"\n{event}: {len(gdf)} buildings classified")
        print(f"Swath coverage: {gdf['swath_coverage_pct'].iloc[0]}%")
        print(gdf["damage_class"].value_counts())