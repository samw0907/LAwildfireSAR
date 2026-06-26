# scripts/check_eaton_buildings.py
import geopandas as gpd

gdf = gpd.read_file("data/vectors/building_damage_eaton.geojson")
print(f"CRS: {gdf.crs}")
print(f"Bounds: {gdf.total_bounds}")
print(f"Sample geometries:\n{gdf.geometry.head()}")
print(f"mean_change_combined sample:\n{gdf['mean_change_combined'].head(10)}")