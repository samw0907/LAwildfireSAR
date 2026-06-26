# src/pipeline/change.py
import os
import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from rasterio.features import shapes
from scipy import ndimage
import geopandas as gpd
from shapely.geometry import shape
from src.utils.config import load_config


def load_composite(path):
    """Load a composite GeoTIFF and return array and profile."""
    with rasterio.open(path) as src:
        data = src.read(1).astype(np.float32)
        profile = src.profile.copy()
    return data, profile


def compute_log_ratio(pre, post):
    """
    Compute log-ratio change detection in dB space.
    Subtraction in dB is equivalent to log-ratio in linear space.
    Negative values indicate backscatter decrease (damage signal).
    """
    return post - pre


def compute_combined_magnitude(change_vv, change_vh):
    """
    Combine VV and VH change rasters into a single magnitude layer.
    VH sensitive to vegetation/volume scattering loss.
    VV sensitive to surface roughness and structural change.
    """
    return np.sqrt(change_vv ** 2 + change_vh ** 2)


def clip_to_bbox(array, profile, bbox_lonlat):
    """
    Clip a raster array to a bounding box defined in lon/lat (EPSG:4326).
    Reprojects bbox to raster CRS and returns clipped array and updated profile.
    """
    src_crs = profile["crs"]
    transform = profile["transform"]

    lon_min, lat_min, lon_max, lat_max = bbox_lonlat
    left, bottom, right, top = transform_bounds(
        CRS.from_epsg(4326), src_crs,
        lon_min, lat_min, lon_max, lat_max
    )

    window = from_bounds(left, bottom, right, top, transform)
    window = window.round_lengths().round_offsets()

    col_off = max(0, int(window.col_off))
    row_off = max(0, int(window.row_off))
    col_end = min(array.shape[1], col_off + int(window.width))
    row_end = min(array.shape[0], row_off + int(window.height))

    clipped = array[row_off:row_end, col_off:col_end]

    # Update transform to reflect clipped origin
    new_transform = transform * rasterio.transform.Affine.translation(col_off, row_off)
    new_profile = profile.copy()
    new_profile.update(
        width=clipped.shape[1],
        height=clipped.shape[0],
        transform=new_transform
    )

    return clipped, new_profile


def apply_burn_mask(combined, threshold):
    """
    Apply threshold to combined change magnitude to produce binary burn mask.
    Pixels with magnitude above threshold are classified as changed.
    Returns binary mask array (1 = changed, 0 = unchanged).
    """
    mask = np.zeros_like(combined, dtype=np.uint8)
    mask[combined >= threshold] = 1
    return mask


def remove_small_patches(mask, min_pixels):
    """
    Remove isolated changed pixel groups smaller than min_pixels.
    Uses connected component labelling to identify and filter small patches.
    """
    labeled, num_features = ndimage.label(mask)
    if num_features == 0:
        return mask
    sizes = ndimage.sum(mask, labeled, range(1, num_features + 1))
    remove_labels = [
        i + 1 for i, size in enumerate(sizes) if size < min_pixels
    ]
    for label in remove_labels:
        mask[labeled == label] = 0
    return mask


def vectorise_mask(mask, profile):
    """
    Convert binary raster mask to GeoJSON-compatible GeoDataFrame.
    Returns a GeoDataFrame of burn patch polygons with area in hectares.
    """
    transform = profile["transform"]
    crs = profile["crs"]

    polygons = []
    for geom, val in shapes(mask, transform=transform):
        if val == 1:
            polygons.append(shape(geom))

    if not polygons:
        return gpd.GeoDataFrame(columns=["geometry", "area_ha"], crs=crs)

    gdf = gpd.GeoDataFrame(geometry=polygons, crs=crs)
    # Area in hectares (CRS is UTM metres)
    gdf["area_ha"] = gdf.geometry.area / 10000
    return gdf


def write_raster(array, profile, output_path):
    """Write a numpy array to GeoTIFF using the provided profile."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    out_profile = profile.copy()
    out_profile.update(dtype=rasterio.float32, count=1, nodata=np.nan)
    with rasterio.open(output_path, "w", **out_profile) as dst:
        dst.write(array.astype(np.float32), 1)


def write_mask(array, profile, output_path):
    """Write a binary uint8 mask to GeoTIFF."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    out_profile = profile.copy()
    out_profile.update(dtype=rasterio.uint8, count=1, nodata=0)
    with rasterio.open(output_path, "w", **out_profile) as dst:
        dst.write(array.astype(np.uint8), 1)


def run_change_detection(composites=None, config=None):
    """
    Main change detection function.
    Computes VV and VH log-ratio and combined magnitude over full swath.
    Clips to fire AOI for mask, patch removal and vectorisation.
    Returns dict of output paths and burn mask GeoDataFrame.
    """
    if config is None:
        config = load_config()

    analysis_dir = os.path.join("data", "analysis")
    threshold = config["change_detection"]["threshold_combined_db"]

    # Minimum patch size: 0.1 ha at 20m pixel spacing = 25 pixels
    pixel_area_ha = (config["processing"]["spacing"] ** 2) / 10000
    min_pixels = int(0.1 / pixel_area_ha)

    print("Loading composites...")
    pre_vv, profile = load_composite(
        os.path.join(analysis_dir, "pre_composite_VV.tif")
    )
    post_vv, _ = load_composite(
        os.path.join(analysis_dir, "post_composite_VV.tif")
    )
    pre_vh, _ = load_composite(
        os.path.join(analysis_dir, "pre_composite_VH.tif")
    )
    post_vh, _ = load_composite(
        os.path.join(analysis_dir, "post_composite_VH.tif")
    )

    # Crop all arrays to minimum common shape to handle sub-pixel
    # alignment differences between scenes
    min_rows = min(pre_vv.shape[0], post_vv.shape[0],
                   pre_vh.shape[0], post_vh.shape[0])
    min_cols = min(pre_vv.shape[1], post_vv.shape[1],
                   pre_vh.shape[1], post_vh.shape[1])

    pre_vv  = pre_vv[:min_rows, :min_cols]
    post_vv = post_vv[:min_rows, :min_cols]
    pre_vh  = pre_vh[:min_rows, :min_cols]
    post_vh = post_vh[:min_rows, :min_cols]
    profile.update(width=min_cols, height=min_rows)

    print("Computing change detection...")
    change_vv = compute_log_ratio(pre_vv, post_vv)
    change_vh = compute_log_ratio(pre_vh, post_vh)
    combined = compute_combined_magnitude(change_vv, change_vh)

    # Write full swath change rasters — preserved for visualisation
    print("Writing full swath change rasters...")
    write_raster(change_vv, profile, os.path.join(analysis_dir, "change_vv.tif"))
    write_raster(change_vh, profile, os.path.join(analysis_dir, "change_vh.tif"))
    write_raster(combined, profile, os.path.join(analysis_dir, "change_combined.tif"))

    # Clip to combined fire AOI before masking and vectorisation
    # reduces processing area from full swath to fire extent only
    print("Clipping to fire AOI...")
    combined_bbox = config["study_area"]["combined_bbox"]
    combined_clipped, clipped_profile = clip_to_bbox(combined, profile, combined_bbox)
    print(f"Clipped array shape: {combined_clipped.shape}")

    # Apply threshold and remove small patches on clipped area
    print(f"Applying burn mask threshold: {threshold} dB combined magnitude...")
    burn_mask = apply_burn_mask(combined_clipped, threshold)
    burn_mask = remove_small_patches(burn_mask, min_pixels)

    # Write clipped burn mask
    write_mask(
        burn_mask, clipped_profile,
        os.path.join(analysis_dir, "burn_mask_full.tif")
    )

    # Vectorise burn mask
    print("Vectorising burn mask...")
    burn_gdf = vectorise_mask(burn_mask, clipped_profile)
    total_area = burn_gdf["area_ha"].sum()
    print(f"Total detected burn area: {total_area:.1f} ha across {len(burn_gdf)} patches")

    vectors_dir = os.path.join("data", "vectors")
    os.makedirs(vectors_dir, exist_ok=True)
    burn_path = os.path.join(vectors_dir, "burn_perimeter_full.geojson")
    burn_gdf.to_file(burn_path, driver="GeoJSON")
    print(f"Written: {burn_path}")

    outputs = {
        "change_vv": os.path.join(analysis_dir, "change_vv.tif"),
        "change_vh": os.path.join(analysis_dir, "change_vh.tif"),
        "change_combined": os.path.join(analysis_dir, "change_combined.tif"),
        "burn_mask_full": os.path.join(analysis_dir, "burn_mask_full.tif"),
        "burn_perimeter": burn_path,
        "burn_gdf": burn_gdf,
        "total_area_ha": total_area,
    }

    print("\nChange detection complete.")
    return outputs


if __name__ == "__main__":
    outputs = run_change_detection()
    print(f"\nTotal burn area: {outputs['total_area_ha']:.1f} ha")
    print(f"Patch count: {len(outputs['burn_gdf'])}")