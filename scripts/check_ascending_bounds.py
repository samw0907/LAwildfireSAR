# scripts/check_ascending_bounds.py
# Verify ascending scene coverage against both fire perimeters before downloading

import geopandas as gpd
from src.utils.config import load_config, get_cdse_credentials
from src.pipeline.download import get_access_token, search_scene

config = load_config()
user, password = get_cdse_credentials()
token = get_access_token(user, password)

# Check one ascending scene footprint from CDSE metadata
result = search_scene(
    config["study_area"]["combined_bbox"],
    "2025-01-14",
    "ASCENDING",
    config
)

if result:
    print("Scene name:", result["Name"])
    print("Scene footprint:", result.get("GeoFootprint", "not available"))
    print("Scene ContentDate:", result.get("ContentDate", "not available"))
    print("Full metadata keys:", list(result.keys()))
else:
    print("No scene found")