# src/pipeline/download.py
import os
import requests
from datetime import datetime, timedelta
from src.utils.config import load_config, get_cdse_credentials


def get_access_token(user, password):
    """Authenticate with CDSE and return an access token."""
    response = requests.post(
        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
        data={
            "client_id": "cdse-public",
            "username": user,
            "password": password,
            "grant_type": "password",
        },
    )
    response.raise_for_status()
    return response.json()["access_token"]


def search_scene(bbox, date_str, orbit_direction, config):
    """
    Search CDSE for a single Sentinel-1 IW GRD scene for a given date,
    bounding box and orbit direction.
    Returns the first matching product metadata dict, or None if not found.
    """
    lon_min, lat_min, lon_max, lat_max = bbox
    date_start = f"{date_str}T00:00:00.000Z"
    date_end = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime(
        "%Y-%m-%dT00:00:00.000Z"
    )
    product_type = config["scenes"]["product_type"]

    url = (
        "https://catalogue.dataspace.copernicus.eu/odata/v1/Products?"
        f"$filter=Collection/Name eq 'SENTINEL-1' "
        f"and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' "
        f"and att/OData.CSC.StringAttribute/Value eq '{product_type}') "
        f"and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'orbitDirection' "
        f"and att/OData.CSC.StringAttribute/Value eq '{orbit_direction}') "
        f"and ContentDate/Start gt {date_start} "
        f"and ContentDate/Start lt {date_end} "
        f"and OData.CSC.Intersects(area=geography'SRID=4326;POLYGON(("
        f"{lon_min} {lat_min},{lon_max} {lat_min},"
        f"{lon_max} {lat_max},{lon_min} {lat_max},"
        f"{lon_min} {lat_min}))')"
        f"&$top=5"
    )

    response = requests.get(url)
    response.raise_for_status()
    results = response.json().get("value", [])
    return results[0] if results else None


def select_orbit_direction(bbox, all_dates, config, token):
    """
    Check coverage for both ASCENDING and DESCENDING across all dates.
    Returns the orbit direction with complete coverage.
    Prefers DESCENDING if both are complete.
    Raises an error if neither direction has complete coverage.
    """
    print("Checking orbit direction coverage across all dates...")
    candidates = ["DESCENDING", "ASCENDING"]
    coverage = {}

    for direction in candidates:
        found = []
        missing = []
        for date_str in all_dates:
            result = search_scene(bbox, date_str, direction, config)
            if result:
                found.append(date_str)
            else:
                missing.append(date_str)
        coverage[direction] = {"found": found, "missing": missing}
        print(f"  {direction}: {len(found)}/{len(all_dates)} dates found"
              + (f" — missing: {missing}" if missing else " — complete"))

    # Select direction with complete coverage, prefer DESCENDING
    for direction in candidates:
        if not coverage[direction]["missing"]:
            print(f"\nSelected orbit direction: {direction}")
            return direction

    # Neither complete — raise with detail
    raise RuntimeError(
        f"Neither orbit direction has complete scene coverage.\n"
        f"DESCENDING missing: {coverage['DESCENDING']['missing']}\n"
        f"ASCENDING missing: {coverage['ASCENDING']['missing']}"
    )


def download_scene(product, token, output_dir):
    """
    Download a single Sentinel-1 scene to output_dir.
    Skips download if file already exists.
    Returns the local file path.
    """
    product_id = product["Id"]
    product_name = product["Name"]
    output_path = os.path.join(output_dir, f"{product_name}.zip")

    if os.path.exists(output_path):
        print(f"Already exists, skipping: {product_name}")
        return output_path

    print(f"Downloading: {product_name}")
    url = f"https://download.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value"

    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        stream=True,
    )
    response.raise_for_status()

    os.makedirs(output_dir, exist_ok=True)
    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    print(f"Downloaded: {product_name}")
    return output_path


def run_download(config=None):
    """
    Main download function.
    Checks orbit direction coverage first, then downloads all scenes
    from the selected direction.
    Returns a scene inventory dict keyed by date.
    """
    if config is None:
        config = load_config()

    user, password = get_cdse_credentials()
    token = get_access_token(user, password)

    bbox = config["study_area"]["combined_bbox"]
    output_dir = config["paths"]["raw_scenes"]
    all_dates = config["scenes"]["pre"] + config["scenes"]["post"]

    # Select orbit direction with complete coverage before downloading anything
    orbit_direction = select_orbit_direction(bbox, all_dates, config, token)

    inventory = {}

    for date_str in all_dates:
        scene_type = "pre" if date_str in config["scenes"]["pre"] else "post"
        print(f"\nSearching for scene: {date_str} ({scene_type}, {orbit_direction})")

        product = search_scene(bbox, date_str, orbit_direction, config)

        if not product:
            raise RuntimeError(f"Scene not found for {date_str} — this should not happen after coverage check")

        local_path = download_scene(product, token, output_dir)

        inventory[date_str] = {
            "path": local_path,
            "name": product["Name"],
            "type": scene_type,
            "orbit_direction": orbit_direction,
            "product_id": product["Id"],
        }

    print(f"\nDownload complete. {len(inventory)} scenes in inventory.")
    return inventory


if __name__ == "__main__":
    inventory = run_download()
    for date, info in inventory.items():
        print(f"{date} ({info['type']}): {info['name']}")