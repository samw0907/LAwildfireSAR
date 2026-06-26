# scripts/check_raster_eaton.py
import rasterio
import numpy as np

with rasterio.open("data/analysis/change_combined.tif") as src:
    print(f"Bounds: {src.bounds}")
    print(f"Shape: {src.shape}")
    print(f"Nodata: {src.nodata}")

    # Read the eastern portion where Eaton should be
    from rasterio.windows import from_bounds
    # Eaton is roughly at x=392000-406000, y=3780000-3789000 in UTM
    window = from_bounds(390000, 3778000, 410000, 3791000, src.transform)
    data = src.read(1, window=window)
    print(f"\nEaton area window shape: {data.shape}")
    print(f"Valid pixels in Eaton area: {np.sum(~np.isnan(data))}")
    print(f"NaN pixels in Eaton area: {np.sum(np.isnan(data))}")
    print(f"Min value: {np.nanmin(data) if np.any(~np.isnan(data)) else 'all NaN'}")
    print(f"Max value: {np.nanmax(data) if np.any(~np.isnan(data)) else 'all NaN'}")
    