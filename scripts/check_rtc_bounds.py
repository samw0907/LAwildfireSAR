# scripts/check_rtc_bounds.py
import os
import rasterio
import geopandas as gpd

rtc_dir = "data/rtc"
files = [f for f in os.listdir(rtc_dir) if "VV" in f and f.endswith(".tif")]
for f in sorted(files)[:2]:
    with rasterio.open(os.path.join(rtc_dir, f)) as src:
        print(f"Scene: {f}")
        print(f"  Bounds: {src.bounds}")
        print(f"  CRS: {src.crs}")

eaton = gpd.read_file("data/external/eaton_perimeter.geojson")
eaton_utm = eaton.to_crs("EPSG:32611")
print(f"\nEaton bounds (UTM 32611): {eaton_utm.total_bounds}")

with rasterio.open("data/analysis/change_combined.tif") as src:
    print(f"\nChange raster bounds: {src.bounds}")