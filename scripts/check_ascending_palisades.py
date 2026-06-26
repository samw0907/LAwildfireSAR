# scripts/check_ascending_palisades.py
from src.utils.config import load_config, get_cdse_credentials
from src.pipeline.download import get_access_token, search_scene

config = load_config()
user, password = get_cdse_credentials()
token = get_access_token(user, password)

palisades_bbox = [-118.70, 34.02, -118.48, 34.13]
for date in config["scenes"]["pre"] + config["scenes"]["post"]:
    result = search_scene(palisades_bbox, date, "ASCENDING", config)
    print(f"{date}: {result['Name'] if result else 'NOT FOUND'}")