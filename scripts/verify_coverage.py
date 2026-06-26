# scripts/verify_coverage.py
import geopandas as gpd
from shapely.geometry import shape
from src.utils.config import load_config, get_cdse_credentials
from src.pipeline.download import get_access_token, search_scene

config = load_config()
user, password = get_cdse_credentials()
token = get_access_token(user, password)

eaton = gpd.read_file("data/external/eaton_perimeter.geojson")
palisades = gpd.read_file("data/external/palisades_perimeter.geojson")

orbit_direction = config["scenes"].get("orbit_direction", "DESCENDING")

for date in config["scenes"]["pre"] + config["scenes"]["post"]:
    result = search_scene(
        config["study_area"]["combined_bbox"],
        date,
        orbit_direction,
        config
    )
    if not result:
        print(f"FAIL: No scene found for {date}")
        continue

    footprint = shape(result["GeoFootprint"])

    eaton_covered = footprint.contains(eaton.union_all())
    eaton_intersects = footprint.intersects(eaton.union_all())
    palisades_covered = footprint.contains(palisades.union_all())

    # Check what percentage of Eaton is within footprint
    eaton_geom = eaton.union_all()
    intersection = footprint.intersection(eaton_geom)
    coverage_pct = (intersection.area / eaton_geom.area) * 100

    print(f"{date} — Eaton fully contained: {eaton_covered}, "
          f"intersects: {eaton_intersects}, "
          f"coverage: {coverage_pct:.1f}%, "
          f"Palisades contained: {palisades_covered}")