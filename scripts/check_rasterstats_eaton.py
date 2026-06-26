# scripts/check_rasterstats_eaton.py
import geopandas as gpd
import rasterio

buildings = gpd.read_file("data/vectors/building_damage_eaton.geojson").head(5)
centroids = [(geom.centroid.x, geom.centroid.y) for geom in buildings.geometry]

for raster in ["data/analysis/pre_composite_VV.tif",
               "data/analysis/post_composite_VV.tif",
               "data/analysis/change_combined.tif"]:
    with rasterio.open(raster) as src:
        from rasterio.sample import sample_gen
        values = [v[0] for v in sample_gen(src, centroids)]
        print(f"{raster.split('/')[-1]}: {values}")