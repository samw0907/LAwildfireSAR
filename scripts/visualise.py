# scripts/visualise.py
"""
Generate all visualisation outputs for the LA Wildfire SAR damage assessment.

Outputs (outputs/figures/):
  damage_map_eaton.png        building damage classification over basemap
  damage_map_palisades.png    building damage classification over basemap
  damage_map_combined.png     both fires, geographic context
  validation_metrics.png      confusion matrices + precision/recall/F1 bars
  change_signal_dist.png      SAR change signal distribution by DINS damage class
"""
import os
import json
import warnings
import numpy as np
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
import contextily as ctx

warnings.filterwarnings("ignore", category=FutureWarning)

FIGURES_DIR = os.path.join("outputs", "figures")

DAMAGE_COLOURS = {
    "destroyed":         "#d62728",
    "possibly_affected": "#ff7f0e",
    "no_damage":         "#2ca02c",
    "no_data":           "#c7c7c7",
    "geometry_limited":  "#9467bd",
}
DAMAGE_LABELS = {
    "destroyed":         "Destroyed",
    "possibly_affected": "Possibly Affected",
    "no_damage":         "No Damage",
    "no_data":           "No Data (below resolution)",
    "geometry_limited":  "Geometry Limited",
}
VALIDATION_COLOURS = {
    "true_positive":  "#d62728",
    "false_positive": "#ff7f0e",
    "false_negative": "#1f77b4",
    "true_negative":  "#2ca02c",
}

BASEMAP_PROVIDER = ctx.providers.CartoDB.Positron


def _to_webmercator(gdf):
    return gdf.to_crs("EPSG:3857")


def _add_basemap(ax, zoom="auto"):
    try:
        ctx.add_basemap(ax, source=BASEMAP_PROVIDER, zoom=zoom, attribution_size=6)
    except Exception as e:
        print(f"  Basemap unavailable ({e}) — continuing without")


def _damage_legend_handles(classes):
    return [
        mpatches.Patch(color=DAMAGE_COLOURS[c], label=DAMAGE_LABELS[c])
        for c in classes if c in DAMAGE_COLOURS
    ]


def plot_damage_map(buildings_gdf, perimeter_gdf, event_name, output_path):
    """
    Plot building footprints coloured by damage class over a web-tile basemap.
    Includes fire perimeter outline and legend with headline statistics.
    """
    buildings_wm = _to_webmercator(buildings_gdf)
    perimeter_wm = _to_webmercator(perimeter_gdf)

    fig, ax = plt.subplots(figsize=(14, 11))

    # Draw no_data first (bottom layer) so classified buildings render on top
    for cls in ["no_data", "geometry_limited", "no_damage", "possibly_affected", "destroyed"]:
        subset = buildings_wm[buildings_wm["damage_class"] == cls]
        if len(subset) == 0:
            continue
        markersize = 3 if cls == "no_data" else 5
        alpha = 0.4 if cls == "no_data" else 0.85
        subset.plot(ax=ax, color=DAMAGE_COLOURS[cls], markersize=markersize,
                    alpha=alpha, zorder=3 if cls != "no_data" else 2)

    # Fire perimeter
    perimeter_wm.boundary.plot(ax=ax, color="#222222", linewidth=1.4,
                               linestyle="--", zorder=4, label="Fire perimeter")

    _add_basemap(ax)

    # Statistics annotation
    total = len(buildings_gdf)
    n_dest = (buildings_gdf["damage_class"] == "destroyed").sum()
    n_pa   = (buildings_gdf["damage_class"] == "possibly_affected").sum()
    n_nd   = (buildings_gdf["damage_class"] == "no_damage").sum()
    n_nodata = (buildings_gdf["damage_class"] == "no_data").sum()

    stats_text = (
        f"Total buildings:  {total:,}\n"
        f"Destroyed:        {n_dest:,}  ({100*n_dest/total:.1f}%)\n"
        f"Possibly affected:{n_pa:,}  ({100*n_pa/total:.1f}%)\n"
        f"No damage:        {n_nd:,}  ({100*n_nd/total:.1f}%)\n"
        f"No data:          {n_nodata:,}  ({100*n_nodata/total:.1f}%)"
    )
    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
            fontsize=8.5, verticalalignment="top", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.85))

    # Legend
    classes_present = [c for c in ["destroyed", "possibly_affected", "no_damage",
                                   "no_data", "geometry_limited"]
                       if (buildings_gdf["damage_class"] == c).any()]
    handles = _damage_legend_handles(classes_present)
    handles.append(mpatches.Patch(color="#222222", label="Fire perimeter"))
    ax.legend(handles=handles, loc="lower right", fontsize=9, framealpha=0.9)

    event_title = "Eaton Fire" if event_name == "eaton" else "Palisades Fire"
    ax.set_title(
        f"SAR Building Damage Assessment — {event_title}\n"
        f"Sentinel-1 Ascending Track 64 | Pre: Dec 2024 | Post: Jan–Feb 2025",
        fontsize=12, fontweight="bold", pad=10
    )
    ax.set_axis_off()

    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Written: {output_path}")


def plot_combined_map(eaton_gdf, palisades_gdf, eaton_perim, palisades_perim, output_path):
    """
    Overview map showing both fires in geographic context.
    """
    combined = gpd.GeoDataFrame(
        pd.concat([_to_webmercator(eaton_gdf),
                   _to_webmercator(palisades_gdf)], ignore_index=True),
        crs="EPSG:3857"
    )
    eaton_wm    = _to_webmercator(eaton_perim)
    palisades_wm = _to_webmercator(palisades_perim)

    fig, ax = plt.subplots(figsize=(16, 10))

    for cls in ["no_data", "geometry_limited", "no_damage", "possibly_affected", "destroyed"]:
        subset = combined[combined["damage_class"] == cls]
        if len(subset) == 0:
            continue
        alpha = 0.35 if cls == "no_data" else 0.8
        ms = 3 if cls == "no_data" else 5
        subset.plot(ax=ax, color=DAMAGE_COLOURS[cls], markersize=ms, alpha=alpha, zorder=3)

    eaton_wm.boundary.plot(ax=ax, color="#111111", linewidth=1.2,
                           linestyle="--", zorder=4)
    palisades_wm.boundary.plot(ax=ax, color="#111111", linewidth=1.2,
                               linestyle="--", zorder=4)

    _add_basemap(ax, zoom=11)

    # Event labels
    for gdf_wm, label in [(eaton_wm, "Eaton Fire"), (palisades_wm, "Palisades Fire")]:
        centroid = gdf_wm.union_all().centroid
        ax.annotate(label, xy=(centroid.x, centroid.y),
                    fontsize=11, fontweight="bold", color="#111111",
                    ha="center", va="bottom", zorder=5,
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.7))

    classes_present = [c for c in ["destroyed", "possibly_affected", "no_damage", "no_data"]
                       if (combined["damage_class"] == c).any()]
    handles = _damage_legend_handles(classes_present)
    handles.append(mpatches.Patch(color="#111111", label="Fire perimeter"))
    ax.legend(handles=handles, loc="lower right", fontsize=9, framealpha=0.9)

    ax.set_title(
        "LA Wildfires 2025 — SAR Building Damage Assessment\n"
        "Sentinel-1 Ascending Track 64 | Eaton & Palisades Fires",
        fontsize=13, fontweight="bold", pad=10
    )
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Written: {output_path}")


def plot_validation_metrics(metrics, output_path):
    """
    Three-panel figure:
      Left:   confusion matrix heatmaps for Eaton and Palisades
      Right:  precision / recall / F1 / accuracy bar chart per event
    """
    fig = plt.figure(figsize=(16, 7))
    gs = GridSpec(1, 3, figure=fig, wspace=0.35)

    ax_eaton  = fig.add_subplot(gs[0, 0])
    ax_palis  = fig.add_subplot(gs[0, 1])
    ax_bars   = fig.add_subplot(gs[0, 2])

    event_labels = {"eaton": "Eaton Fire", "palisades": "Palisades Fire"}
    cm_axes = {"eaton": ax_eaton, "palisades": ax_palis}

    for event, ax in cm_axes.items():
        m = metrics[event]
        cm = np.array([[m["tn"], m["fp"]],
                       [m["fn"], m["tp"]]])
        im = ax.imshow(cm, interpolation="nearest", cmap="Blues")
        ax.set_title(f"{event_labels[event]}\nConfusion Matrix", fontsize=11, fontweight="bold")
        ax.set_xlabel("Predicted", fontsize=9)
        ax.set_ylabel("Actual (DINS)", fontsize=9)
        ax.set_xticks([0, 1])
        ax.set_yticks([0, 1])
        ax.set_xticklabels(["Not Damaged", "Damaged"], fontsize=8)
        ax.set_yticklabels(["Not Damaged", "Damaged"], fontsize=8)
        for i in range(2):
            for j in range(2):
                ax.text(j, i, f"{cm[i, j]:,}",
                        ha="center", va="center",
                        color="white" if cm[i, j] > cm.max() * 0.5 else "black",
                        fontsize=11, fontweight="bold")
        ax.text(0.5, -0.14,
                f"Precision: {m['precision']}  Recall: {m['recall']}  F1: {m['f1']}",
                ha="center", transform=ax.transAxes, fontsize=8.5,
                bbox=dict(boxstyle="round,pad=0.3", fc="#f0f0f0", alpha=0.9))

    # Bar chart — precision / recall / F1 / accuracy
    bar_metrics = ["precision", "recall", "f1", "accuracy"]
    bar_labels   = ["Precision", "Recall", "F1", "Accuracy"]
    x = np.arange(len(bar_metrics))
    width = 0.35
    colours = ["#1f77b4", "#ff7f0e"]

    for i, (event, colour) in enumerate(zip(["eaton", "palisades"], colours)):
        vals = [metrics[event][m] for m in bar_metrics]
        bars = ax_bars.bar(x + i * width, vals, width, label=event_labels[event],
                           color=colour, alpha=0.85)
        for bar, val in zip(bars, vals):
            ax_bars.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                         f"{val:.3f}", ha="center", va="bottom", fontsize=8)

    ax_bars.set_ylim(0, 1.05)
    ax_bars.set_xticks(x + width / 2)
    ax_bars.set_xticklabels(bar_labels, fontsize=9)
    ax_bars.set_ylabel("Score", fontsize=9)
    ax_bars.set_title("Validation Metrics\nby Event", fontsize=11, fontweight="bold")
    ax_bars.legend(fontsize=9)
    ax_bars.axhline(0.8, color="grey", linewidth=0.8, linestyle=":", alpha=0.7)
    ax_bars.text(3.55, 0.81, "0.8", color="grey", fontsize=7.5)
    ax_bars.set_ylim(0, 1.1)

    fig.suptitle(
        "LA Wildfires 2025 — SAR Damage Assessment Validation against CAL FIRE DINS\n"
        f"Threshold: 2.9 dB combined change magnitude | "
        f"Eaton: {metrics['eaton']['validated_records']:,} buildings | "
        f"Palisades: {metrics['palisades']['validated_records']:,} buildings",
        fontsize=10, y=1.01
    )

    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Written: {output_path}")


def plot_change_signal_distribution(eaton_gdf, palisades_gdf,
                                    eaton_dins_path, palisades_dins_path,
                                    target_crs, output_path):
    """
    Violin/box plot showing the distribution of SAR mean_change_combined values
    split by DINS damage category. Demonstrates signal separability.
    """
    import pandas as pd

    def get_joined(buildings_gdf, dins_path, event_label):
        dins = gpd.read_file(dins_path).to_crs(target_crs)
        # Identify damage column
        for col in ["DAMAGE", "damage_cat", "DAMAGE_CAT", "DamageCategory"]:
            if col in dins.columns:
                damage_col = col
                break
        else:
            return None
        joined = gpd.sjoin_nearest(
            dins[["geometry", damage_col]],
            buildings_gdf[["geometry", "damage_class", "mean_change_combined"]],
            how="inner", max_distance=25
        )
        joined = joined[~joined["damage_class"].isin(["no_data", "geometry_limited"])].copy()
        joined = joined[~joined["mean_change_combined"].isna()].copy()
        # Binary DINS label
        joined["dins_binary"] = joined[damage_col].apply(
            lambda x: "Damaged\n(Destroyed/Major)"
            if any(d in str(x).lower() for d in ["destroyed", "major"])
            else "Not Damaged"
        )
        joined["event"] = event_label
        return joined[[damage_col, "dins_binary", "mean_change_combined", "event"]]

    eaton_joined   = get_joined(eaton_gdf,   eaton_dins_path,   "Eaton")
    palisades_joined = get_joined(palisades_gdf, palisades_dins_path, "Palisades")

    if eaton_joined is None or palisades_joined is None:
        print("  Skipping change signal distribution — DINS join failed")
        return

    import pandas as pd
    combined = pd.concat([eaton_joined, palisades_joined], ignore_index=True)

    fig, axes = plt.subplots(1, 2, figsize=(13, 6), sharey=True)

    for ax, event in zip(axes, ["Eaton", "Palisades"]):
        data = combined[combined["event"] == event]
        groups = ["Not Damaged", "Damaged\n(Destroyed/Major)"]
        plot_data = [data[data["dins_binary"] == g]["mean_change_combined"].values
                     for g in groups]
        plot_data = [d[~np.isnan(d)] for d in plot_data]

        parts = ax.violinplot(plot_data, positions=[0, 1], showmedians=True,
                              showextrema=True)
        for i, (pc, colour) in enumerate(zip(parts["bodies"],
                                             ["#2ca02c", "#d62728"])):
            pc.set_facecolor(colour)
            pc.set_alpha(0.6)
        parts["cmedians"].set_color("black")
        parts["cmedians"].set_linewidth(1.5)
        parts["cbars"].set_color("black")
        parts["cmins"].set_color("black")
        parts["cmaxes"].set_color("black")

        # Threshold lines
        ax.axhline(2.9, color="#ff7f0e", linewidth=1.2, linestyle="--",
                   label="Threshold (2.9 dB)")
        ax.axhline(2.9 * 0.6, color="#ff7f0e", linewidth=0.8, linestyle=":",
                   label="Lower threshold (1.74 dB)")

        ax.set_xticks([0, 1])
        ax.set_xticklabels(groups, fontsize=9)
        ax.set_title(f"{event} Fire\n"
                     f"(n={len(plot_data[0]):,} not damaged, "
                     f"n={len(plot_data[1]):,} damaged)",
                     fontsize=10, fontweight="bold")
        ax.set_ylabel("Mean SAR Change Magnitude (dB)", fontsize=9)
        ax.grid(axis="y", alpha=0.3)
        if event == "Eaton":
            ax.legend(fontsize=8, loc="upper left")

    fig.suptitle(
        "SAR Change Signal Separability — Mean Combined Change by DINS Damage Category\n"
        "Sentinel-1 Ascending Track 64 | Log-ratio VV²+VH² combined magnitude",
        fontsize=11, fontweight="bold"
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  Written: {output_path}")


def run_visualisations(config=None):
    """
    Entry point. Loads all outputs from disk and generates all figures.
    """
    import pandas as pd
    from src.utils.config import load_config as _load_config

    if config is None:
        config = _load_config()

    os.makedirs(FIGURES_DIR, exist_ok=True)
    target_crs = f"EPSG:{config['processing']['crs']}"

    print("Loading building damage outputs...")
    eaton_gdf     = gpd.read_file("data/vectors/building_damage_eaton.geojson")
    palisades_gdf = gpd.read_file("data/vectors/building_damage_palisades.geojson")

    print("Loading fire perimeters...")
    eaton_perim     = gpd.read_file("data/external/eaton_perimeter.geojson").to_crs(target_crs)
    palisades_perim = gpd.read_file("data/external/palisades_perimeter.geojson").to_crs(target_crs)

    print("Loading validation metrics...")
    with open("data/validation/validation_summary.json") as f:
        metrics = json.load(f)

    print("\nGenerating figures...")

    print("1/5  Eaton damage map")
    plot_damage_map(
        eaton_gdf, eaton_perim, "eaton",
        os.path.join(FIGURES_DIR, "damage_map_eaton.png")
    )

    print("2/5  Palisades damage map")
    plot_damage_map(
        palisades_gdf, palisades_perim, "palisades",
        os.path.join(FIGURES_DIR, "damage_map_palisades.png")
    )

    print("3/5  Combined overview map")
    plot_combined_map(
        eaton_gdf, palisades_gdf, eaton_perim, palisades_perim,
        os.path.join(FIGURES_DIR, "damage_map_combined.png")
    )

    print("4/5  Validation metrics panel")
    plot_validation_metrics(
        metrics,
        os.path.join(FIGURES_DIR, "validation_metrics.png")
    )

    print("5/5  SAR change signal distribution")
    plot_change_signal_distribution(
        eaton_gdf, palisades_gdf,
        "data/external/calfire_dins_eaton.geojson",
        "data/external/calfire_dins_palisades.geojson",
        target_crs,
        os.path.join(FIGURES_DIR, "change_signal_dist.png")
    )

    print(f"\nAll figures written to {FIGURES_DIR}/")
    return FIGURES_DIR


if __name__ == "__main__":
    import pandas as pd
    run_visualisations()
