# scripts/check_eaton_overlap.py
import geopandas as gpd
import rasterio
from rasterstats import zonal_stats
import numpy as np

# Load a few Eaton buildings
eaton = gpd.read_file("data/external/eaton_perimeter.geojson").to_crs("EPSG:32611")
buildings = gpd.read_file("data/external/California.geojson/California.geojson",
                          bbox=tuple(eaton.total_bounds))
buildings = buildings.to_crs("EPSG:32611")
buildings_in = buildings[buildings.intersects(eaton.union_all())].head(10)

print(f"Sample Eaton buildings bounds: {buildings_in.total_bounds}")

with rasterio.open("data/analysis/change_combined.tif") as src:
    print(f"Change raster bounds: {src.bounds}")
    print(f"Change raster CRS: {src.crs}")
    print(f"Change raster nodata: {src.nodata}")

    # Sample the raster at the center of the first building
    geom = buildings_in.geometry.iloc[0]
    print(f"\nFirst building centroid: {geom.centroid}")

    # Check what value the raster has at that location
    from rasterio.windows import from_bounds
    b = geom.bounds
    window = from_bounds(b[0], b[1], b[2], b[3], src.transform)
    data = src.read(1, window=window)
    print(f"Raster values at first building: {data}")
    print(f"All NaN: {np.all(np.isnan(data))}")

# Run zonal stats on just these 10 buildings
stats = zonal_stats(buildings_in, "data/analysis/change_combined.tif",
                    stats=["mean"], nodata=np.nan)
print(f"\nZonal stats for 10 Eaton buildings: {stats}")