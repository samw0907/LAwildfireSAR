# scripts/check_track64_coverage.py
# Find all Track 64 ascending and Track 71 descending scene dates over Eaton
# and show footprint extents to assess Eaton coverage
import requests
from src.utils.config import load_config, get_cdse_credentials
from src.pipeline.download import get_access_token

config = load_config()
user, password = get_cdse_credentials()
token = get_access_token(user, password)

eaton_bbox = [-118.17, 34.14, -117.98, 34.24]
lon_min, lat_min, lon_max, lat_max = eaton_bbox
wkt = (
    f"POLYGON(({lon_min} {lat_min},{lon_max} {lat_min},"
    f"{lon_max} {lat_max},{lon_min} {lat_max},{lon_min} {lat_min}))"
)

for direction, target_track in [("ASCENDING", 64), ("DESCENDING", 71)]:
    print(f"\n=== {direction} Track {target_track} scenes over Eaton (Dec 2024 - Feb 2025) ===")
    url = (
        "https://catalogue.dataspace.copernicus.eu/odata/v1/Products?"
        "$filter=Collection/Name eq 'SENTINEL-1'"
        " and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType'"
        " and att/OData.CSC.StringAttribute/Value eq 'IW_GRDH_1S')"
        " and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'orbitDirection'"
        f" and att/OData.CSC.StringAttribute/Value eq '{direction}')"
        " and ContentDate/Start gt 2024-12-01T00:00:00.000Z"
        " and ContentDate/Start lt 2025-03-01T00:00:00.000Z"
        f" and OData.CSC.Intersects(area=geography'SRID=4326;{wkt}')"
        "&$top=50&$orderby=ContentDate/Start asc"
        "&$expand=Attributes"
    )
    r = requests.get(url)
    r.raise_for_status()
    results = r.json().get("value", [])

    for s in results:
        name = s["Name"]
        parts = name.split("_")
        abs_orbit = int(parts[6]) if len(parts) > 6 else -1
        rel_orbit = (abs_orbit - 73) % 175 + 1
        if rel_orbit != target_track:
            continue
        date = parts[5][:8]  # YYYYMMDD from start time
        time = parts[5][9:15]  # HHMMSS
        footprint = s.get("GeoFootprint", {})
        coords = footprint.get("coordinates", [[]])[0] if footprint else []
        if coords:
            xs = [c[0] for c in coords]
            ys = [c[1] for c in coords]
            print(f"  {date} {time}Z  |  lon [{min(xs):.2f}, {max(xs):.2f}]  lat [{min(ys):.2f}, {max(ys):.2f}]  |  orbit={abs_orbit}")
        else:
            print(f"  {date} {time}Z  |  no footprint  |  orbit={abs_orbit}")
