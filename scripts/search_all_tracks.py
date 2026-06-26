# scripts/search_all_tracks.py
# Search CDSE for ALL available ascending and descending tracks over Eaton
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

for direction in ["ASCENDING", "DESCENDING"]:
    print(f"\n=== {direction} scenes over Eaton bbox (2024-12-01 to 2025-03-01) ===")
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
    )
    r = requests.get(url)
    r.raise_for_status()
    results = r.json().get("value", [])
    print(f"Found {len(results)} scenes:")
    seen_tracks = {}
    for s in results:
        name = s["Name"]
        # Extract absolute orbit from filename (positions 49-55)
        abs_orbit = int(name.split("_")[6]) if len(name.split("_")) > 6 else -1
        # S1A relative orbit: (abs_orbit - 73) % 175 + 1
        rel_orbit = (abs_orbit - 73) % 175 + 1
        key = rel_orbit
        if key not in seen_tracks:
            seen_tracks[key] = []
        seen_tracks[key].append(name[:65])
    for track, names in sorted(seen_tracks.items()):
        print(f"  Track {track:3d}: {len(names)} scenes — e.g. {names[0]}")
