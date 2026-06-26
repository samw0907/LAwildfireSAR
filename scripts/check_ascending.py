# scripts/check_ascending.py
from src.utils.config import load_config, get_cdse_credentials
from src.pipeline.download import get_access_token, search_scene

config = load_config()
user, password = get_cdse_credentials()
token = get_access_token(user, password)

eaton_bbox = [-118.17, 34.14, -117.98, 34.24]
for date in config["scenes"]["pre"] + config["scenes"]["post"]:
    result = search_scene(eaton_bbox, date, "ASCENDING", config)
    print(f"{date}: {result['Name'] if result else 'NOT FOUND'}")