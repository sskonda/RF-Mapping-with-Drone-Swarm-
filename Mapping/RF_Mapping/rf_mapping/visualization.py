"""Auditable plots for offline probabilistic RF-assisted mapping."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, Normalize, TwoSlopeNorm
from matplotlib.patches import Patch
import numpy as np


def _grid_centers(values: np.ndarray, name: str) -> np.ndarray:
    centers = np.asarray(values, dtype=float)
    if (
        centers.ndim != 1
        or centers.size < 2
        or not np.all(np.isfinite(centers))
        or np.any(np.diff(centers) <= 0.0)
    ):
        raise ValueError(
            f"{name} must be a finite, strictly increasing 1D array "
            "with at least two values"
        )
    return centers


def _grid_edges(centers: np.ndarray) -> np.ndarray:
    midpoints = 0.5 * (centers[:-1] + centers[1:])
    return np.concatenate(
        (
            [centers[0] - 0.5 * (centers[1] - centers[0])],
            midpoints,
            [centers[-1] + 0.5 * (centers[-1] - centers[-2])],
        )
    )


def _xy_array(values: np.ndarray, name: str, *, allow_empty: bool) -> np.ndarray:
    points = np.asarray(values, dtype=float)
    if points.ndim != 2 or points.shape[1:] != (2,):
        raise ValueError(f"{name} must have shape (n, 2)")
    if not allow_empty and points.shape[0] == 0:
        raise ValueError(f"{name} cannot be empty")
    if not np.all(np.isfinite(points)):
        raise ValueError(f"{name} must contain only finite values")
    return points


def _finite_vector(values: np.ndarray, name: str, expected_size: int) -> np.ndarray:
    vector = np.asarray(values, dtype=float)
    if vector.shape != (expected_size,) or not np.all(np.isfinite(vector)):
        raise ValueError(
            f"{name} must be a finite 1D array with {expected_size} values"
        )
    return vector


def _finite_grid(
    values: np.ndarray,
    name: str,
    expected_shape: tuple[int, int],
) -> np.ndarray:
    grid = np.asarray(values, dtype=float)
    if grid.shape != expected_shape:
        raise ValueError(f"{name} must have shape {expected_shape}")
    if not np.all(np.isfinite(grid)):
        raise ValueError(f"{name} must contain only finite values")
    return grid


def _nonconstant_normalize(
    values: np.ndarray,
    *,
    minimum: float | None = None,
) -> Normalize:
    lower = float(np.min(values)) if minimum is None else minimum
    upper = float(np.max(values))
    if upper <= lower:
        upper = lower + 1.0
    return Normalize(vmin=lower, vmax=upper)


def save_inference_figure(
    *,
    output_path: str | Path,
    grid_x_centers_m: np.ndarray,
    grid_y_centers_m: np.ndarray,
    measured_receiver_xy_m: np.ndarray,
    measured_rssi_dbm: np.ndarray,
    posterior_mean_dbm: np.ndarray,
    posterior_standard_deviation_db: np.ndarray,
    support_density: np.ndarray,
    support_label: str,
    extrapolation_mask: np.ndarray,
    excess_attenuation_map: np.ndarray,
    excess_attenuation_units: str,
    bootstrap_evidence_frequency: np.ndarray,
    occupancy_state: np.ndarray,
    ap_positions_xy_m: np.ndarray,
    ap_ids: Sequence[str],
    ray_start_xy_m: np.ndarray,
    ray_end_xy_m: np.ndarray,
    component_labels: np.ndarray | None = None,
    field_ap_id: str | None = None,
    show: bool = False,
) -> Path:
    """Save a six-panel RF inference audit figure and return its path.

    Coordinates are metres in a common physical frame. ``occupancy_state`` uses
    0 for unknown, 1 for sampled/AP cells with limited free evidence, 2 for
    attenuation evidence, and 3 for conflicting evidence. The colors encode
    bootstrap frequency, not physical-object certainty or collision-safe free space.
    """

    destination = Path(output_path)
    if destination.suffix.lower() not in {".png", ".pdf"}:
        raise ValueError("output_path must end in .png or .pdf")
    x_centers = _grid_centers(grid_x_centers_m, "grid_x_centers_m")
    y_centers = _grid_centers(grid_y_centers_m, "grid_y_centers_m")
    x_edges = _grid_edges(x_centers)
    y_edges = _grid_edges(y_centers)
    grid_shape = (y_centers.size, x_centers.size)

    receivers = _xy_array(
        measured_receiver_xy_m, "measured_receiver_xy_m", allow_empty=False
    )
    measured_rssi = _finite_vector(
        measured_rssi_dbm, "measured_rssi_dbm", receivers.shape[0]
    )
    posterior_mean = _finite_grid(
        posterior_mean_dbm, "posterior_mean_dbm", grid_shape
    )
    posterior_std = _finite_grid(
        posterior_standard_deviation_db,
        "posterior_standard_deviation_db",
        grid_shape,
    )
    if np.any(posterior_std < 0.0):
        raise ValueError("posterior_standard_deviation_db cannot be negative")
    density = _finite_grid(support_density, "support_density", grid_shape)
    if np.any(density < 0.0):
        raise ValueError("support_density cannot be negative")
    if not isinstance(support_label, str) or not support_label.strip():
        raise ValueError("support_label must be a non-empty string")
    extrapolated = np.asarray(extrapolation_mask)
    if extrapolated.shape != grid_shape or extrapolated.dtype.kind != "b":
        raise ValueError(
            f"extrapolation_mask must be a boolean array with shape {grid_shape}"
        )
    attenuation = _finite_grid(
        excess_attenuation_map, "excess_attenuation_map", grid_shape
    )
    if (
        not isinstance(excess_attenuation_units, str)
        or not excess_attenuation_units.strip()
    ):
        raise ValueError("excess_attenuation_units must be a non-empty string")
    bootstrap_frequency = _finite_grid(
        bootstrap_evidence_frequency,
        "bootstrap_evidence_frequency",
        grid_shape,
    )
    if np.any((bootstrap_frequency < 0.0) | (bootstrap_frequency > 1.0)):
        raise ValueError("bootstrap frequencies must be in [0, 1]")

    states_raw = np.asarray(occupancy_state)
    if states_raw.shape != grid_shape or not np.all(np.isfinite(states_raw)):
        raise ValueError(
            f"occupancy_state must be a finite array with shape {grid_shape}"
        )
    states = states_raw.astype(int)
    if not np.array_equal(states_raw, states) or not np.all(
        np.isin(states, (0, 1, 2, 3))
    ):
        raise ValueError(
            "occupancy_state values must be 0 (unknown), 1 (limited free evidence), "
            "2 (attenuation evidence), or 3 (conflict)"
        )

    aps = _xy_array(ap_positions_xy_m, "ap_positions_xy_m", allow_empty=True)
    if isinstance(ap_ids, str):
        raise ValueError("ap_ids must be a sequence, not a single string")
    ids = tuple(ap_ids)
    if len(ids) != aps.shape[0] or any(
        not isinstance(value, str) or not value.strip() for value in ids
    ):
        raise ValueError("ap_ids must contain one non-empty string per AP position")
    if field_ap_id is not None and field_ap_id not in ids:
        raise ValueError("field_ap_id must identify one of the plotted APs")
    ray_starts = _xy_array(ray_start_xy_m, "ray_start_xy_m", allow_empty=True)
    ray_ends = _xy_array(ray_end_xy_m, "ray_end_xy_m", allow_empty=True)
    if ray_starts.shape != ray_ends.shape:
        raise ValueError("ray_start_xy_m and ray_end_xy_m must have matching shapes")

    labels: np.ndarray | None = None
    if component_labels is not None:
        raw_labels = np.asarray(component_labels)
        if raw_labels.shape != grid_shape or not np.all(np.isfinite(raw_labels)):
            raise ValueError(
                f"component_labels must be a finite array with shape {grid_shape}"
            )
        labels = raw_labels.astype(int)
        if not np.array_equal(raw_labels, labels) or np.any(labels < 0):
            raise ValueError("component_labels must contain non-negative integers")

    all_x = np.concatenate(
        (x_edges, receivers[:, 0], aps[:, 0], ray_starts[:, 0], ray_ends[:, 0])
    )
    all_y = np.concatenate(
        (y_edges, receivers[:, 1], aps[:, 1], ray_starts[:, 1], ray_ends[:, 1])
    )
    x_minimum, x_maximum = float(np.min(all_x)), float(np.max(all_x))
    y_minimum, y_maximum = float(np.min(all_y)), float(np.max(all_y))
    x_padding = 0.03 * (x_maximum - x_minimum)
    y_padding = 0.03 * (y_maximum - y_minimum)
    x_limits = (x_minimum - x_padding, x_maximum + x_padding)
    y_limits = (y_minimum - y_padding, y_maximum + y_padding)

    def add_context(
        axis: plt.Axes,
        *,
        include_rays: bool,
    ) -> None:
        if include_rays:
            for start, end in zip(ray_starts, ray_ends):
                axis.plot(
                    [start[0], end[0]],
                    [start[1], end[1]],
                    color="black",
                    linewidth=0.65,
                    alpha=0.16,
                    zorder=3,
                )
        axis.scatter(
            receivers[:, 0],
            receivers[:, 1],
            s=22,
            facecolors="none",
            edgecolors="black",
            linewidths=0.8,
            zorder=5,
        )
        axis.scatter(
            aps[:, 0],
            aps[:, 1],
            marker="*",
            s=155,
            c=["#26c6da" if value == field_ap_id else "#ffd54f" for value in ids],
            edgecolors="black",
            linewidths=0.8,
            zorder=6,
        )
        for identifier, position in zip(ids, aps):
            display_identifier = (
                identifier if len(identifier) <= 14 else identifier[:11] + "..."
            )
            if identifier == field_ap_id:
                display_identifier += " (field)"
            axis.annotate(
                display_identifier,
                position,
                xytext=(5, 5),
                textcoords="offset points",
                fontsize=8,
                weight="bold",
                zorder=7,
            )

    def add_extrapolation_hatch(axis: plt.Axes) -> None:
        if np.any(extrapolated):
            axis.contourf(
                x_centers,
                y_centers,
                extrapolated.astype(float),
                levels=[0.5, 1.5],
                colors="none",
                hatches=["////"],
                zorder=8,
            )

    def finish_axis(axis: plt.Axes) -> None:
        axis.set_xlim(x_limits)
        axis.set_ylim(y_limits)
        axis.set_aspect("equal", adjustable="box")
        axis.set_xlabel("x (m)")
        axis.set_ylabel("y (m)")

    destination.parent.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(2, 3, figsize=(17.0, 10.5), constrained_layout=True)
    figure.suptitle(
        "Probabilistic RF-assisted mapping: estimates are not measured geometry",
        fontsize=14,
    )

    rssi_norm = _nonconstant_normalize(
        np.concatenate((measured_rssi, posterior_mean.ravel()))
    )
    measured_axis = axes[0, 0]
    add_context(measured_axis, include_rays=False)
    measured_plot = measured_axis.scatter(
        receivers[:, 0],
        receivers[:, 1],
        c=measured_rssi,
        cmap="viridis",
        norm=rssi_norm,
        s=65,
        edgecolors="black",
        linewidths=0.7,
        zorder=6,
    )
    figure.colorbar(measured_plot, ax=measured_axis, label="RSSI (dBm)", shrink=0.82)
    measured_axis.set_title("Measured RSSI")
    finish_axis(measured_axis)

    mean_axis = axes[0, 1]
    mean_plot = mean_axis.pcolormesh(
        x_edges,
        y_edges,
        posterior_mean,
        cmap="viridis",
        norm=rssi_norm,
        shading="flat",
    )
    add_context(mean_axis, include_rays=False)
    add_extrapolation_hatch(mean_axis)
    mean_axis.legend(
        handles=[
            Patch(
                facecolor="none",
                edgecolor="black",
                hatch="////",
                label="Extrapolation",
            )
        ],
        loc="best",
        fontsize=8,
    )
    figure.colorbar(
        mean_plot,
        ax=mean_axis,
        label="Posterior mean RSSI (dBm)",
        shrink=0.82,
    )
    mean_axis.set_title("Estimated RF posterior mean")
    finish_axis(mean_axis)

    std_axis = axes[0, 2]
    std_plot = std_axis.pcolormesh(
        x_edges,
        y_edges,
        posterior_std,
        cmap="cividis",
        norm=_nonconstant_normalize(posterior_std, minimum=0.0),
        shading="flat",
    )
    add_context(std_axis, include_rays=False)
    add_extrapolation_hatch(std_axis)
    figure.colorbar(
        std_plot,
        ax=std_axis,
        label="Posterior standard deviation (dB)",
        shrink=0.82,
    )
    std_axis.set_title("Posterior standard deviation")
    finish_axis(std_axis)

    support_axis = axes[1, 0]
    support_plot = support_axis.pcolormesh(
        x_edges,
        y_edges,
        density,
        cmap="Blues",
        norm=_nonconstant_normalize(density, minimum=0.0),
        shading="flat",
    )
    add_context(support_axis, include_rays=True)
    add_extrapolation_hatch(support_axis)
    figure.colorbar(
        support_plot,
        ax=support_axis,
        label=support_label.strip(),
        shrink=0.82,
    )
    support_axis.set_title("Data/link support")
    finish_axis(support_axis)

    attenuation_axis = axes[1, 1]
    attenuation_minimum = float(np.min(attenuation))
    attenuation_maximum = float(np.max(attenuation))
    if attenuation_minimum < 0.0 < attenuation_maximum:
        attenuation_norm: Normalize = TwoSlopeNorm(
            vmin=attenuation_minimum,
            vcenter=0.0,
            vmax=attenuation_maximum,
        )
        attenuation_cmap = "coolwarm"
    else:
        attenuation_norm = _nonconstant_normalize(
            attenuation,
            minimum=0.0 if attenuation_minimum >= 0.0 else None,
        )
        attenuation_cmap = "magma"
    attenuation_plot = attenuation_axis.pcolormesh(
        x_edges,
        y_edges,
        attenuation,
        cmap=attenuation_cmap,
        norm=attenuation_norm,
        shading="flat",
    )
    add_context(attenuation_axis, include_rays=True)
    add_extrapolation_hatch(attenuation_axis)
    figure.colorbar(
        attenuation_plot,
        ax=attenuation_axis,
        label=f"Excess attenuation ({excess_attenuation_units.strip()})",
        shrink=0.82,
    )
    attenuation_axis.set_title("Excess attenuation estimate")
    finish_axis(attenuation_axis)

    evidence_axis = axes[1, 2]
    evidence_plot = evidence_axis.pcolormesh(
        x_edges,
        y_edges,
        bootstrap_frequency,
        cmap="inferno",
        norm=Normalize(vmin=0.0, vmax=1.0),
        shading="flat",
    )
    unknown = np.ma.masked_where(states != 0, np.zeros(grid_shape))
    limited_free = np.ma.masked_where(states != 1, np.zeros(grid_shape))
    conflict = np.ma.masked_where(states != 3, np.zeros(grid_shape))
    evidence_axis.pcolormesh(
        x_edges,
        y_edges,
        unknown,
        cmap=ListedColormap(["#8d8d8d"]),
        vmin=0.0,
        vmax=1.0,
        shading="flat",
        alpha=0.94,
    )
    evidence_axis.pcolormesh(
        x_edges,
        y_edges,
        limited_free,
        cmap=ListedColormap(["#6baed6"]),
        vmin=0.0,
        vmax=1.0,
        shading="flat",
        alpha=0.82,
    )
    evidence_axis.pcolormesh(
        x_edges,
        y_edges,
        conflict,
        cmap=ListedColormap(["#7b3294"]),
        vmin=0.0,
        vmax=1.0,
        shading="flat",
        alpha=0.9,
    )
    if labels is not None:
        for component_id in np.unique(labels[labels > 0]):
            component_mask = labels == component_id
            rows, columns = np.nonzero(component_mask)
            evidence_axis.text(
                float(np.mean(x_centers[columns])),
                float(np.mean(y_centers[rows])),
                f"C{component_id}",
                color="white",
                fontsize=8,
                weight="bold",
                ha="center",
                va="center",
                zorder=6,
            )
    add_context(evidence_axis, include_rays=True)
    add_extrapolation_hatch(evidence_axis)
    legend_handles: list[Patch] = [
        Patch(facecolor="#8d8d8d", label="Unknown (not navigation-safe)"),
        Patch(facecolor="#6baed6", label="Sampled/AP cell (limited free evidence)"),
        Patch(facecolor="#f05a28", label="Potential attenuation evidence"),
        Patch(facecolor="#7b3294", label="Conflicting free/attenuation evidence"),
    ]
    evidence_axis.legend(handles=legend_handles, loc="best", fontsize=7)
    figure.colorbar(
        evidence_plot,
        ax=evidence_axis,
        label="Bootstrap attenuation-evidence frequency (0–1)",
        shrink=0.82,
    )
    evidence_axis.set_title("Obstacle/attenuation evidence")
    finish_axis(evidence_axis)

    try:
        metadata = (
            {"CreationDate": None, "ModDate": None}
            if destination.suffix.lower() == ".pdf"
            else None
        )
        figure.savefig(destination, dpi=170, metadata=metadata)
        if show:
            plt.show()
    finally:
        plt.close(figure)
    return destination
