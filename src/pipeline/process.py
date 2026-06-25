# src/pipeline/process.py
import os
from pyroSAR.snap import geocode
from spatialist import Vector
from src.utils.config import load_config


def process_scene(scene_path, config):
    """
    Process a single Sentinel-1 GRD scene to radiometrically terrain
    corrected (RTC) backscatter GeoTIFF using pyroSAR/SNAP.
    Skips processing if output already exists.
    Returns the output directory path.
    """
    outdir = config["paths"]["rtc_output"]
    os.makedirs(outdir, exist_ok=True)

    spacing = config["processing"]["spacing"]
    crs = config["processing"]["crs"]
    polarizations = config["processing"]["polarizations"]
    dem = config["processing"]["dem"]
    snap_aux = config["paths"]["snap_aux"]

    # Set SNAP auxiliary data path so orbit files and DEM tiles
    # are stored in a consistent location between runs
    os.environ["SNAP_AUX_PATH"] = snap_aux

    print(f"Processing: {os.path.basename(scene_path)}")

    geocode(
        infile=scene_path,
        outdir=outdir,
        shapefile=None,             # no AOI clip at this stage, clip in analysis
        t_srs=crs,                  # EPSG:32611 UTM Zone 11N
        spacing=spacing,            # 20m output pixel spacing
        polarizations=polarizations,
        scaling="dB",               # output in decibels
        removeS1BorderNoise=True,
        removeS1BorderNoiseMethod="pyroSAR",
        removeS1ThermalNoise=True,
        geocoding_type="Range-Doppler",
        terrainFlattening=True,     # radiometric terrain correction
        demName=dem,                # SRTM 1Sec HGT, auto-downloaded by SNAP
        speckleFilter=False,        # applied separately after RTC
        refarea="gamma0",           # gamma nought backscatter convention
        export_extra=["localIncidenceAngle"],
        cleanup=True,
    )

    print(f"Processing complete: {os.path.basename(scene_path)}")
    return outdir


def run_processing(inventory, config=None):
    """
    Process all scenes in the inventory dict.
    Skips scenes already processed (pyroSAR handles this internally).
    Returns updated inventory with rtc_dir added per scene.
    """
    if config is None:
        config = load_config()

    print(f"\nProcessing {len(inventory)} scenes...")

    for date_str, info in inventory.items():
        scene_path = info["path"]
        rtc_dir = process_scene(scene_path, config)
        inventory[date_str]["rtc_dir"] = rtc_dir

    print("\nAll scenes processed.")
    return inventory


if __name__ == "__main__":
    # For testing a single scene independently
    config = load_config()
    test_scene = input("Enter path to a downloaded .zip scene: ").strip()
    process_scene(test_scene, config)