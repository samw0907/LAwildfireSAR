# scripts/check_buildings_crs.py
import geopandas as gpd

# Just read a tiny sample without bbox filter
gdf = gpd.read_file(
    "data/external/California.geojson/California.geojson",
    rows=5
)
print(f"CRS: {gdf.crs}")
print(f"Sample bounds: {gdf.total_bounds}")
print(f"Sample geometries:\n{gdf.geometry}")