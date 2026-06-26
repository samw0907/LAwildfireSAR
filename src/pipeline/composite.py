# src/pipeline/composite.py
import os
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from src.utils.config import load_config


def find_rtc_file(rtc_dir, date_str, polarisation):
    """
    Find the RTC GeoTIFF for a given date and polarisation in the rtc directory.
    pyroSAR naming convention: S1A_IW__D_{timestamp}_{polarisation}_gamma0-rtc_db.tif
    Returns the file path or raises if not found.
    """
    date_compact = date_str.replace("-", "")[:8]
    matches = [
        f for f in os.listdir(rtc_dir)
        if date_compact in f
        and polarisation in f
        and f.endswith(".tif")
        and "gamma0-rtc" in f
    ]
    if not matches:
        raise FileNotFoundError(
            f"No RTC file found for {date_str} {polarisation} in {rtc_dir}"
        )
    if len(matches) > 1:
        print(f"  Warning: multiple matches for {date_str} {polarisation}, using first: {matches[0]}")
    return os.path.join(rtc_dir, matches[0])


def align_to_reference(src_path, ref_profile):
    """
    Read a raster and warp it to match the reference profile (crs, transform, shape).
    Returns a numpy array aligned to the reference grid.
    """
    with rasterio.open(src_path) as src:
        with WarpedVRT(
            src,
            crs=ref_profile["crs"],
            transform=ref_profile["transform"],
            width=ref_profile["width"],
            height=ref_profile["height"],
            resampling=Resampling.bilinear,
        ) as vrt:
            return vrt.read(1)


def build_composite(rtc_dir, dates, polarisation, output_path, config, ref_profile=None):
    """
    Build a mean composite from multiple RTC scenes for a given polarisation.
    Aligns all scenes to ref_profile's grid before averaging. If ref_profile is
    not supplied, the first scene's grid is used.
    Writes output as GeoTIFF. Skips if output already exists.
    """
    if os.path.exists(output_path):
        print(f"  Already exists, skipping: {os.path.basename(output_path)}")
        return output_path

    print(f"  Building {polarisation} composite from {len(dates)} scenes...")

    # Use supplied reference profile or derive from first scene
    if ref_profile is None:
        ref_path = find_rtc_file(rtc_dir, dates[0], polarisation)
        with rasterio.open(ref_path) as ref:
            ref_profile = ref.profile.copy()

    stack = []

    # Align every scene (including the first) to the reference grid
    for date_str in dates:
        scene_path = find_rtc_file(rtc_dir, date_str, polarisation)
        aligned = align_to_reference(scene_path, ref_profile)
        stack.append(aligned)

    # Pixel-wise median, ignoring nodata.
    # Median is more robust than mean to a single anomalous scene
    # (e.g. a rain event causing wet-soil backscatter spike in one acquisition).
    stack_array = np.array(stack, dtype=np.float32)
    nodata = ref_profile.get("nodata", None)
    if nodata is not None:
        stack_array[stack_array == nodata] = np.nan
    composite = np.nanmedian(stack_array, axis=0)

    # Write output
    out_profile = ref_profile.copy()
    out_profile.update(dtype=rasterio.float32, count=1, nodata=np.nan)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with rasterio.open(output_path, "w", **out_profile) as dst:
        dst.write(composite.astype(np.float32), 1)

    print(f"  Written: {os.path.basename(output_path)}")
    return output_path


def run_composites(config=None):
    """
    Build pre and post composites for VV and VH polarisations.
    Returns a dict of composite paths keyed by period and polarisation.
    """
    if config is None:
        config = load_config()

    rtc_dir = config["paths"]["rtc_output"]
    pre_dates = config["scenes"]["pre"]
    post_dates = config["scenes"]["post"]
    polarisations = config["processing"]["polarizations"]
    out_dir = os.path.join("data", "analysis")

    composites = {}

    # Establish a single master reference grid from the first pre-event VV scene.
    # All four composites (pre/post × VV/VH) are aligned to this grid so that
    # change.py can do pixel-wise subtraction on spatially registered arrays.
    first_pre_path = find_rtc_file(rtc_dir, pre_dates[0], polarisations[0])
    with rasterio.open(first_pre_path) as ref:
        master_ref_profile = ref.profile.copy()
    print(f"Master reference grid: {os.path.basename(first_pre_path)}")
    print(f"  Origin: ({master_ref_profile['transform'].c:.1f}, {master_ref_profile['transform'].f:.1f})")
    print(f"  Size: {master_ref_profile['width']} x {master_ref_profile['height']}")

    for pol in polarisations:
        print(f"\nBuilding composites for {pol}...")

        pre_path = os.path.join(out_dir, f"pre_composite_{pol}.tif")
        post_path = os.path.join(out_dir, f"post_composite_{pol}.tif")

        composites[f"pre_{pol}"] = build_composite(
            rtc_dir, pre_dates, pol, pre_path, config, ref_profile=master_ref_profile
        )
        composites[f"post_{pol}"] = build_composite(
            rtc_dir, post_dates, pol, post_path, config, ref_profile=master_ref_profile
        )

    print("\nComposites complete.")
    return composites


if __name__ == "__main__":
    composites = run_composites()
    for key, path in composites.items():
        print(f"{key}: {path}")