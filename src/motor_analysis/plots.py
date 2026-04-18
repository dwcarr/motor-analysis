from __future__ import annotations

import html
from pathlib import Path

import numpy as np

from .analysis import AXES, AnalysisConfig, zero_order_hold
from .rrd import ScalarStream


def write_exemplar_plots(
    output_dir: Path,
    streams: dict[str, ScalarStream],
    movement_rows: list[dict[str, object]],
    shot_rows: list[dict[str, object]],
    config: AnalysisConfig,
) -> list[dict[str, object]]:
    """Write representative movement and firing SVG plots and return a manifest."""

    plot_dir = output_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    exemplars: list[dict[str, object]] = []

    for axis in AXES:
        for size_label, lo, hi, target_mag in [
            ("small angle movement", 1.0, 3.0, 2.0),
            ("large angle movement", 20.0, float("inf"), 30.0),
        ]:
            row = _choose_movement(movement_rows, axis, lo, hi, target_mag)
            if row is None:
                continue
            file_name = f"movement_{axis}_{'small' if lo < 5 else 'large'}.svg"
            description = (
                f"{axis.capitalize()} {size_label}: "
                f"{float(row['initial_target_deg']):.2f} deg to {float(row['final_target_deg']):.2f} deg "
                f"({float(row['magnitude_deg']):.2f} deg move)."
            )
            _write_movement_plot(plot_dir / file_name, streams, row, config, description)
            exemplars.append(
                {
                    "kind": "movement",
                    "category": size_label,
                    "label": f"{axis.capitalize()} {size_label}",
                    "file": f"plots/{file_name}",
                    "axis": axis,
                    "episode_idx": int(row["episode_idx"]),
                    "event_idx": "",
                    "start_time_s": float(row["start_time_s"]),
                    "end_time_s": float(row["end_time_s"]),
                    "description": description,
                }
            )

    for category, row in _choose_shots(shot_rows).items():
        file_name = f"shot_{category}.svg"
        label = _shot_category_label(category)
        description = _shot_description(label, row)
        _write_shot_plot(plot_dir / file_name, streams, row, config, description)
        exemplars.append(
            {
                "kind": "shot",
                "category": label,
                "label": label.capitalize(),
                "file": f"plots/{file_name}",
                "axis": "",
                "episode_idx": "",
                "event_idx": int(row["event_idx"]),
                "start_time_s": float(row["fire_time_s"]),
                "end_time_s": "",
                "description": description,
            }
        )

    return exemplars


def write_outlier_inspection_page(
    output_dir: Path,
    streams: dict[str, ScalarStream],
    movement_rows: list[dict[str, object]],
    config: AnalysisConfig,
    *,
    min_magnitude_deg: float = 8.0,
    max_arrival_latency_s: float = 0.02,
    per_axis: int = 6,
) -> list[dict[str, object]]:
    """
    Write a separate HTML page for large step-like movements with near-zero arrival.

    This intentionally does not modify the main report. It is a diagnostic page
    for inspecting whether low-latency / large-angle points are real responses or
    artifacts of target sequencing, short holds, or already-moving mechanisms.
    """

    plot_dir = output_dir / "outliers"
    plot_dir.mkdir(parents=True, exist_ok=True)
    rows = _choose_arrival_outliers(movement_rows, min_magnitude_deg, max_arrival_latency_s, per_axis)
    manifest: list[dict[str, object]] = []

    for index, row in enumerate(rows, start=1):
        axis = str(row["axis"])
        file_name = f"{index:02d}_{axis}_episode_{int(row['episode_idx'])}.svg"
        description = _outlier_description(row)
        _write_movement_plot(
            plot_dir / file_name,
            streams,
            row,
            config,
            f"{axis.capitalize()} low-latency outlier: episode {int(row['episode_idx'])}",
        )
        manifest.append(
            {
                "axis": axis,
                "episode_idx": int(row["episode_idx"]),
                "file": f"outliers/{file_name}",
                "magnitude_deg": float(row["magnitude_deg"]),
                "arrival_latency_s": float(row["arrival_latency_s"]),
                "settling_time_s": float(row["settling_time_s"]),
                "target_hold_after_s": float(row["target_hold_after_s"]),
                "initial_target_deg": float(row["initial_target_deg"]),
                "final_target_deg": float(row["final_target_deg"]),
                "target_update_count": int(row["target_update_count"]),
                "target_largest_step_fraction": float(row["target_largest_step_fraction"]),
                "description": description,
            }
        )

    (output_dir / "outlier_inspection.html").write_text(
        _outlier_html(manifest, min_magnitude_deg, max_arrival_latency_s),
        encoding="utf-8",
    )
    return manifest


def write_motion_disturbance_page(
    output_dir: Path,
    streams: dict[str, ScalarStream],
    shot_rows: list[dict[str, object]],
    config: AnalysisConfig,
    *,
    examples: int = 24,
    min_vector_deg: float = 0.25,
    min_target_motion_deg: float = 1.0,
) -> list[dict[str, object]]:
    """
    Write a separate page of firing disturbances while the turret is moving.

    Example selection covers the observed starting-angle space rather than only
    the largest disturbances, because the goal is to inspect behavior under
    motion at different pitch/yaw orientations.
    """

    plot_dir = output_dir / "motion_disturbance"
    plot_dir.mkdir(parents=True, exist_ok=True)
    enriched = _enrich_motion_shot_rows(streams, shot_rows, config)
    rows = _choose_motion_disturbance_examples(
        enriched,
        examples=examples,
        min_vector_deg=min_vector_deg,
        min_target_motion_deg=min_target_motion_deg,
    )
    manifest: list[dict[str, object]] = []

    for index, row in enumerate(rows, start=1):
        file_name = f"{index:02d}_event_{int(row['event_idx'])}.svg"
        description = _motion_disturbance_description(row)
        _write_motion_disturbance_plot(
            plot_dir / file_name,
            streams,
            row,
            config,
            f"Motion disturbance example {index}: event {int(row['event_idx'])}",
        )
        manifest.append(
            {
                "event_idx": int(row["event_idx"]),
                "file": f"motion_disturbance/{file_name}",
                "fire_time_s": float(row["fire_time_s"]),
                "pitch_starting_actual_deg": float(row["pitch_starting_actual_deg"]),
                "yaw_starting_actual_deg": float(row["yaw_starting_actual_deg"]),
                "pitch_starting_target_deg": float(row["pitch_starting_target_deg"]),
                "yaw_starting_target_deg": float(row["yaw_starting_target_deg"]),
                "pitch_target_range_deg": float(row["pitch_target_range_deg"]),
                "yaw_target_range_deg": float(row["yaw_target_range_deg"]),
                "target_motion_vector_deg": float(row["target_motion_vector_deg"]),
                "pitch_peak_abs_deg": float(row["pitch_peak_abs_deg"]),
                "yaw_peak_abs_deg": float(row["yaw_peak_abs_deg"]),
                "disturbance_vector_abs_deg": float(row["disturbance_vector_abs_deg"]),
                "pitch_peak_time_s": float(row["pitch_peak_time_s"]),
                "yaw_peak_time_s": float(row["yaw_peak_time_s"]),
                "fire_to_muzzle_s": float(row["fire_to_muzzle_s"]),
                "fire_to_impact_s": float(row["fire_to_impact_s"]),
                "description": description,
            }
        )

    (output_dir / "motion_disturbance.html").write_text(
        _motion_disturbance_html(manifest, examples, min_vector_deg, min_target_motion_deg),
        encoding="utf-8",
    )
    return manifest


def _choose_movement(
    rows: list[dict[str, object]],
    axis: str,
    low_mag: float,
    high_mag: float,
    target_mag: float,
) -> dict[str, object] | None:
    candidates: list[tuple[float, dict[str, object]]] = []
    for row in rows:
        if row["axis"] != axis:
            continue
        magnitude = float(row["magnitude_deg"])
        if not low_mag <= magnitude < high_mag:
            continue
        settling = float(row["settling_time_s"])
        arrival = float(row["arrival_latency_s"])
        lag = float(row["trajectory_lag_s"])
        hold = float(row["target_hold_after_s"])
        duration = float(row["duration_s"])
        is_step_like = int(row.get("is_step_like_target", 0)) == 1
        if not all(np.isfinite(value) for value in [settling, arrival, lag]):
            continue
        if not is_step_like:
            continue
        if hold < settling + 0.15:
            continue
        if duration > (2.0 if high_mag < 10.0 else 4.0):
            continue
        target_duration = 0.75 if high_mag < 10.0 else 1.5
        largest_fraction = float(row.get("target_largest_step_fraction", 0.0))
        score = (
            abs(magnitude - target_mag)
            + 0.15 * abs(duration - target_duration)
            + 0.20 * settling
            - 0.10 * largest_fraction
        )
        candidates.append((score, row))

    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def _choose_arrival_outliers(
    rows: list[dict[str, object]],
    min_magnitude_deg: float,
    max_arrival_latency_s: float,
    per_axis: int,
) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    for axis in AXES:
        candidates = [
            row
            for row in rows
            if row["axis"] == axis
            and int(row.get("is_step_like_target", 0)) == 1
            and np.isfinite(float(row.get("arrival_latency_s", np.nan)))
            and float(row["arrival_latency_s"]) <= max_arrival_latency_s
            and float(row["magnitude_deg"]) >= min_magnitude_deg
        ]
        candidates.sort(
            key=lambda row: (
                float(row["arrival_latency_s"]),
                float(row["target_hold_after_s"]),
                -float(row["magnitude_deg"]),
            )
        )
        selected.extend(candidates[:per_axis])
    return selected


def _enrich_motion_shot_rows(
    streams: dict[str, ScalarStream],
    rows: list[dict[str, object]],
    config: AnalysisConfig,
) -> list[dict[str, object]]:
    enriched: list[dict[str, object]] = []
    for row in rows:
        copied = dict(row)
        fire_time_s = float(row["fire_time_s"])
        for axis in AXES:
            current = streams[f"/motors/position/{axis}/current"]
            target = streams[f"/motors/position/{axis}/target"]
            copied[f"{axis}_starting_actual_deg"] = float(
                zero_order_hold(current.time_s, current.value, np.array([fire_time_s]))[0]
            )
            copied[f"{axis}_starting_target_deg"] = float(
                zero_order_hold(target.time_s, target.value, np.array([fire_time_s]))[0]
            )
            endpoints = zero_order_hold(
                target.time_s,
                target.value,
                np.array([fire_time_s - config.shot_pre_s, fire_time_s + config.shot_post_s]),
            )
            copied[f"{axis}_target_delta_window_deg"] = float(endpoints[1] - endpoints[0])

        pitch_range = float(copied.get("pitch_target_range_deg", np.nan))
        yaw_range = float(copied.get("yaw_target_range_deg", np.nan))
        copied["target_motion_vector_deg"] = float(np.sqrt(pitch_range * pitch_range + yaw_range * yaw_range))
        enriched.append(copied)
    return enriched


def _choose_motion_disturbance_examples(
    rows: list[dict[str, object]],
    *,
    examples: int,
    min_vector_deg: float,
    min_target_motion_deg: float,
) -> list[dict[str, object]]:
    candidates = [
        row
        for row in rows
        if int(row.get("stable_target", 0)) == 0
        and _finite(row.get("pitch_starting_actual_deg"))
        and _finite(row.get("yaw_starting_actual_deg"))
        and _finite(row.get("disturbance_vector_abs_deg"))
        and _finite(row.get("target_motion_vector_deg"))
        and float(row["disturbance_vector_abs_deg"]) >= min_vector_deg
        and float(row["target_motion_vector_deg"]) >= min_target_motion_deg
    ]
    if len(candidates) < examples:
        existing = {int(row["event_idx"]) for row in candidates}
        relaxed = [
            row
            for row in rows
            if int(row.get("stable_target", 0)) == 0
            and int(row["event_idx"]) not in existing
            and _finite(row.get("pitch_starting_actual_deg"))
            and _finite(row.get("yaw_starting_actual_deg"))
            and _finite(row.get("disturbance_vector_abs_deg"))
        ]
        candidates.extend(relaxed)

    if len(candidates) <= examples:
        return sorted(candidates, key=_starting_angle_sort_key)

    coords = np.array(
        [
            [float(row["pitch_starting_actual_deg"]), float(row["yaw_starting_actual_deg"])]
            for row in candidates
        ],
        dtype=float,
    )
    lo = np.nanmin(coords, axis=0)
    span = np.nanmax(coords, axis=0) - lo
    span[span <= 0.0] = 1.0
    normalized = (coords - lo) / span

    selected: list[int] = []
    seeds = [
        int(np.argmin(normalized[:, 0])),
        int(np.argmax(normalized[:, 0])),
        int(np.argmin(normalized[:, 1])),
        int(np.argmax(normalized[:, 1])),
    ]
    for idx in seeds:
        if idx not in selected:
            selected.append(idx)
        if len(selected) >= examples:
            break

    while len(selected) < examples:
        remaining = [idx for idx in range(len(candidates)) if idx not in selected]
        selected_coords = normalized[np.array(selected, dtype=int)]
        best_idx = max(
            remaining,
            key=lambda idx: (
                float(np.min(np.linalg.norm(selected_coords - normalized[idx], axis=1))),
                float(candidates[idx]["target_motion_vector_deg"]),
                float(candidates[idx]["disturbance_vector_abs_deg"]),
            ),
        )
        selected.append(best_idx)

    return sorted((candidates[idx] for idx in selected), key=_starting_angle_sort_key)


def _starting_angle_sort_key(row: dict[str, object]) -> tuple[float, float, int]:
    return (
        float(row["yaw_starting_actual_deg"]),
        float(row["pitch_starting_actual_deg"]),
        int(row["event_idx"]),
    )


def _choose_shots(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {
        "not_stable": _choose_not_stable_shot(rows),
        "stable_non_trivial": _choose_stable_nontrivial_shot(rows),
    }


def _choose_not_stable_shot(rows: list[dict[str, object]]) -> dict[str, object]:
    candidates = [
        row
        for row in rows
        if int(row["stable_target"]) == 0
        and np.isfinite(float(row["pitch_recovery_s"]))
        and np.isfinite(float(row["yaw_recovery_s"]))
    ]
    if not candidates:
        candidates = [row for row in rows if int(row["stable_target"]) == 0]
    vectors = np.array([float(row["disturbance_vector_abs_deg"]) for row in candidates])
    target = float(np.percentile(vectors[np.isfinite(vectors)], 90))
    return min(candidates, key=lambda row: abs(float(row["disturbance_vector_abs_deg"]) - target))


def _choose_stable_nontrivial_shot(rows: list[dict[str, object]]) -> dict[str, object]:
    candidates = [row for row in rows if int(row["valid_disturbance_shot"]) == 1]
    vectors = np.array([float(row["disturbance_vector_abs_deg"]) for row in candidates])
    target = float(np.median(vectors))
    return min(candidates, key=lambda row: abs(float(row["disturbance_vector_abs_deg"]) - target))


def _write_movement_plot(
    path: Path,
    streams: dict[str, ScalarStream],
    row: dict[str, object],
    config: AnalysisConfig,
    title: str,
) -> None:
    axis = str(row["axis"])
    current = streams[f"/motors/position/{axis}/current"]
    target = streams[f"/motors/position/{axis}/target"]
    start_s = float(row["start_time_s"])
    end_s = float(row["end_time_s"])
    arrival_s = _finite_or_none(row["arrival_latency_s"])
    settling_s = _finite_or_none(row["settling_time_s"])
    post_s = max(value for value in [0.25, arrival_s or 0.0, settling_s or 0.0])
    window_start = start_s - 0.35
    window_end = min(end_s + post_s + 0.30, end_s + float(row["target_hold_after_s"]) - 0.03)
    if window_end <= end_s + 0.20:
        window_end = min(end_s + 0.50, end_s + max(float(row["target_hold_after_s"]), 0.20))

    query_t, actual = _window_series(current, window_start, window_end)
    commanded = zero_order_hold(target.time_s, target.value, query_t)
    rel_t = query_t - start_s
    markers = [
        {"x": 0.0, "label": "start", "color": "#5a6675"},
        {"x": end_s - start_s, "label": "final target", "color": "#5a6675"},
    ]
    if arrival_s is not None:
        markers.append({"x": end_s + arrival_s - start_s, "label": "arrive", "color": "#347a3a", "label_dy": 12})
    if settling_s is not None:
        markers.append({"x": end_s + settling_s - start_s, "label": "settled", "color": "#8a5a00", "label_dy": 34})
    next_target_x = end_s + float(row["target_hold_after_s"]) - start_s
    if next_target_x > end_s - start_s and next_target_x <= window_end - start_s:
        markers.append({"x": next_target_x, "label": "next target", "color": "#9a3412", "label_dy": 56})

    panel = {
        "title": f"{axis.capitalize()} position",
        "ylabel": "degrees",
        "series": [
            {"label": "commanded target", "x": rel_t, "y": commanded, "color": "#48525f", "dash": True},
            {"label": "actual current", "x": rel_t, "y": actual, "color": _axis_color(axis), "dash": False},
        ],
    }
    subtitle = (
        f"Arrival {_fmt_s(arrival_s)}; settling {_fmt_s(settling_s)}; "
        f"trajectory lag {_fmt_s(float(row['trajectory_lag_s']))}."
    )
    path.write_text(_svg_time_series(title, subtitle, [panel], markers), encoding="utf-8")


def _write_shot_plot(
    path: Path,
    streams: dict[str, ScalarStream],
    row: dict[str, object],
    config: AnalysisConfig,
    title: str,
) -> None:
    fire_time = float(row["fire_time_s"])
    recoveries = [
        _finite_or_none(row["pitch_recovery_s"]),
        _finite_or_none(row["yaw_recovery_s"]),
        _finite_or_none(row["fire_to_impact_s"]),
    ]
    post_s = max([config.shot_post_s, *[value for value in recoveries if value is not None]])
    window_start = fire_time - max(0.20, config.shot_pre_s)
    window_end = fire_time + post_s + 0.25
    panels = []

    for axis in AXES:
        current = streams[f"/motors/position/{axis}/current"]
        target = streams[f"/motors/position/{axis}/target"]
        query_t, actual = _window_series(current, window_start, window_end)
        commanded = zero_order_hold(target.time_s, target.value, query_t)
        panels.append(
            {
                "title": f"{axis.capitalize()} position",
                "ylabel": "degrees",
                "series": [
                    {
                        "label": f"{axis} target",
                        "x": query_t - fire_time,
                        "y": commanded,
                        "color": "#48525f",
                        "dash": True,
                    },
                    {
                        "label": f"{axis} actual",
                        "x": query_t - fire_time,
                        "y": actual,
                        "color": _axis_color(axis),
                        "dash": False,
                    },
                ],
            }
        )

    markers = [{"x": 0.0, "label": "fire", "color": "#20242a"}]
    for key, label, color in [
        ("fire_to_muzzle_s", "muzzle", "#6b7280"),
        ("fire_to_impact_s", "impact", "#6b7280"),
    ]:
        value = _finite_or_none(row[key])
        if value is not None and value <= window_end - fire_time:
            markers.append({"x": value, "label": label, "color": color})
    for axis in AXES:
        peak = _finite_or_none(row[f"{axis}_peak_time_s"])
        recovery = _finite_or_none(row[f"{axis}_recovery_s"])
        if peak is not None:
            markers.append({"x": peak, "label": f"{axis} peak", "color": _axis_color(axis), "label_dy": 12})
        if recovery is not None:
            markers.append({"x": recovery, "label": f"{axis} recovered", "color": _axis_color(axis), "label_dy": 34})

    subtitle = (
        f"Pitch peak {float(row['pitch_peak_abs_deg']):.2f} deg; "
        f"yaw peak {float(row['yaw_peak_abs_deg']):.2f} deg; "
        f"vector {float(row['disturbance_vector_abs_deg']):.2f} deg."
    )
    path.write_text(_svg_time_series(title, subtitle, panels, markers), encoding="utf-8")


def _write_motion_disturbance_plot(
    path: Path,
    streams: dict[str, ScalarStream],
    row: dict[str, object],
    config: AnalysisConfig,
    title: str,
) -> None:
    fire_time = float(row["fire_time_s"])
    visible_events = [
        _finite_or_none(row["fire_to_muzzle_s"]),
        _finite_or_none(row["fire_to_impact_s"]),
        _finite_or_none(row["pitch_peak_time_s"]),
        _finite_or_none(row["yaw_peak_time_s"]),
    ]
    post_s = max([config.shot_post_s, *[value for value in visible_events if value is not None]])
    window_start = fire_time - max(0.25, config.shot_pre_s)
    window_end = fire_time + post_s + 0.25
    panels: list[dict[str, object]] = []

    for axis in AXES:
        current = streams[f"/motors/position/{axis}/current"]
        target = streams[f"/motors/position/{axis}/target"]
        query_t, actual = _window_series(current, window_start, window_end)
        commanded = zero_order_hold(target.time_s, target.value, query_t)
        panels.append(
            {
                "title": f"{axis.capitalize()} position",
                "ylabel": "degrees",
                "series": [
                    {"label": "target", "x": query_t - fire_time, "y": commanded, "color": "#48525f", "dash": True},
                    {
                        "label": f"{axis} actual",
                        "x": query_t - fire_time,
                        "y": actual,
                        "color": _axis_color(axis),
                        "dash": False,
                    },
                ],
            }
        )

    for axis in AXES:
        current = streams[f"/motors/position/{axis}/current"]
        target = streams[f"/motors/position/{axis}/target"]
        query_t, actual = _window_series(current, window_start, window_end)
        commanded = zero_order_hold(target.time_s, target.value, query_t)
        deviation = _tracking_error_deviation(query_t, actual, commanded, fire_time, config)
        panels.append(
            {
                "title": f"{axis.capitalize()} disturbance while moving",
                "ylabel": "degrees",
                "series": [
                    {
                        "label": f"{axis} disturbance",
                        "x": query_t - fire_time,
                        "y": deviation,
                        "color": _axis_color(axis),
                        "dash": False,
                    },
                    {
                        "label": "zero baseline",
                        "x": query_t - fire_time,
                        "y": np.zeros_like(deviation),
                        "color": "#8a94a3",
                        "dash": True,
                    },
                ],
            }
        )

    markers = [{"x": 0.0, "label": "fire", "color": "#20242a"}]
    for key, label, color in [
        ("fire_to_muzzle_s", "muzzle", "#6b7280"),
        ("fire_to_impact_s", "impact", "#6b7280"),
    ]:
        value = _finite_or_none(row[key])
        if value is not None and value <= window_end - fire_time:
            markers.append({"x": value, "label": label, "color": color})
    for axis in AXES:
        peak = _finite_or_none(row[f"{axis}_peak_time_s"])
        if peak is not None:
            markers.append({"x": peak, "label": f"{axis} peak", "color": _axis_color(axis), "label_dy": 12})

    subtitle = (
        f"Start pitch {float(row['pitch_starting_actual_deg']):.1f} deg, "
        f"yaw {float(row['yaw_starting_actual_deg']):.1f} deg; "
        f"target motion {float(row['target_motion_vector_deg']):.1f} deg; "
        f"disturbance vector {float(row['disturbance_vector_abs_deg']):.2f} deg."
    )
    path.write_text(_svg_time_series(title, subtitle, panels, markers), encoding="utf-8")


def _tracking_error_deviation(
    query_t: np.ndarray,
    actual: np.ndarray,
    commanded: np.ndarray,
    fire_time: float,
    config: AnalysisConfig,
) -> np.ndarray:
    error = actual - commanded
    baseline_mask = (query_t >= fire_time - config.shot_pre_s) & (
        query_t < fire_time - config.shot_baseline_ignore_s
    )
    if np.any(baseline_mask):
        baseline = float(np.median(error[baseline_mask]))
    else:
        before_fire = query_t < fire_time
        baseline = float(np.median(error[before_fire])) if np.any(before_fire) else float(error[0])
    return error - baseline


def _svg_time_series(
    title: str,
    subtitle: str,
    panels: list[dict[str, object]],
    markers: list[dict[str, object]],
) -> str:
    width = 980
    panel_h = 230
    top = 108
    left = 70
    right = 24
    gap = 38
    bottom = 44
    height = top + len(panels) * panel_h + (len(panels) - 1) * gap + bottom
    plot_w = width - left - right

    x_min = min(float(np.nanmin(series["x"])) for panel in panels for series in panel["series"])
    x_max = max(float(np.nanmax(series["x"])) for panel in panels for series in panel["series"])
    x_pad = max(0.02, (x_max - x_min) * 0.03)
    x_min -= x_pad
    x_max += x_pad

    def sx(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * plot_w

    pieces = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img">',
        "<style>",
        ".axis{stroke:#718096;stroke-width:1}.grid{stroke:#e5eaf0;stroke-width:1}.label{font:12px sans-serif;fill:#5a6675}.title{font:700 18px sans-serif;fill:#20242a}.subtitle{font:12px sans-serif;fill:#5a6675}.panel-title{font:700 13px sans-serif;fill:#20242a}",
        "</style>",
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text class="title" x="{left}" y="28">{html.escape(title)}</text>',
        f'<text class="subtitle" x="{left}" y="50">{html.escape(subtitle)}</text>',
    ]

    legend_x = left
    legend_y = 76
    legend_items = _legend_items(panels)
    for item in legend_items:
        dash = ' stroke-dasharray="6 4"' if item["dash"] else ""
        pieces.append(
            f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 24}" y2="{legend_y}" '
            f'stroke="{item["color"]}" stroke-width="2"{dash}/>'
        )
        pieces.append(f'<text class="label" x="{legend_x + 30}" y="{legend_y + 4}">{html.escape(item["label"])}</text>')
        legend_x += max(130, len(item["label"]) * 7 + 54)

    x_ticks = _ticks(x_min, x_max, 7)
    for panel_idx, panel in enumerate(panels):
        y_top = top + panel_idx * (panel_h + gap)
        y_bottom = y_top + panel_h
        series_items = panel["series"]
        all_y = np.concatenate([np.asarray(series["y"], dtype=float) for series in series_items])
        y_min = float(np.nanmin(all_y))
        y_max = float(np.nanmax(all_y))
        y_pad = max(0.1, (y_max - y_min) * 0.12)
        y_min -= y_pad
        y_max += y_pad
        if y_max <= y_min:
            y_max = y_min + 1.0

        def sy(value: float) -> float:
            return y_bottom - (value - y_min) / (y_max - y_min) * panel_h

        y_ticks = _ticks(y_min, y_max, 5)
        pieces.append(f'<text class="panel-title" x="{left}" y="{y_top - 12}">{html.escape(str(panel["title"]))}</text>')
        for tick in y_ticks:
            y = sy(tick)
            pieces.append(f'<line class="grid" x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}"/>')
            pieces.append(f'<text class="label" x="{left - 8}" y="{y + 4:.2f}" text-anchor="end">{tick:.1f}</text>')
        for tick in x_ticks:
            x = sx(tick)
            pieces.append(f'<line class="grid" x1="{x:.2f}" y1="{y_top}" x2="{x:.2f}" y2="{y_bottom}"/>')
            if panel_idx == len(panels) - 1:
                pieces.append(f'<text class="label" x="{x:.2f}" y="{y_bottom + 20}" text-anchor="middle">{tick:.2f}</text>')
        for marker in markers:
            x = sx(float(marker["x"]))
            if left <= x <= left + plot_w:
                pieces.append(
                    f'<line x1="{x:.2f}" y1="{y_top}" x2="{x:.2f}" y2="{y_bottom}" '
                    f'stroke="{marker["color"]}" stroke-width="1.2" opacity="0.55"/>'
                )
                if panel_idx == 0:
                    label_dy = float(marker.get("label_dy", 12))
                    label_y = y_top + label_dy
                    pieces.append(
                        f'<text class="label" x="{x + 4:.2f}" y="{label_y:.2f}" '
                        f'transform="rotate(-35 {x + 4:.2f} {label_y:.2f})">{html.escape(str(marker["label"]))}</text>'
                    )
        for series in series_items:
            dash = ' stroke-dasharray="6 4"' if series.get("dash") else ""
            pieces.append(
                f'<path d="{_path_data(series["x"], series["y"], sx, sy)}" '
                f'fill="none" stroke="{series["color"]}" stroke-width="2"{dash}/>'
            )
        pieces.append(f'<line class="axis" x1="{left}" y1="{y_bottom}" x2="{left + plot_w}" y2="{y_bottom}"/>')
        pieces.append(f'<line class="axis" x1="{left}" y1="{y_top}" x2="{left}" y2="{y_bottom}"/>')
        pieces.append(
            f'<text class="label" x="18" y="{y_top + panel_h / 2:.2f}" '
            f'transform="rotate(-90 18 {y_top + panel_h / 2:.2f})" text-anchor="middle">{html.escape(str(panel["ylabel"]))}</text>'
        )

    pieces.append(f'<text class="label" x="{left + plot_w / 2}" y="{height - 8}" text-anchor="middle">time relative to event (s)</text>')
    pieces.append("</svg>")
    return "\n".join(pieces)


def _outlier_html(
    rows: list[dict[str, object]],
    min_magnitude_deg: float,
    max_arrival_latency_s: float,
) -> str:
    cards = []
    for row in rows:
        cards.append(
            "<figure>"
            f'<img src="{html.escape(str(row["file"]))}" alt="{html.escape(str(row["axis"]))} episode {row["episode_idx"]}">'
            f"<figcaption>{html.escape(str(row['description']))}</figcaption>"
            "</figure>"
        )
    table = _outlier_table(rows)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Arrival Latency Outlier Inspection</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #20242a; background: #f6f8fa; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 30px 18px 54px; }}
    h1 {{ margin: 0 0 8px; font-size: 32px; }}
    p {{ color: #5a6675; line-height: 1.45; }}
    figure {{ margin: 22px 0 32px; }}
    img {{ width: 100%; display: block; background: #fff; border: 1px solid #c9d1db; border-radius: 8px; }}
    figcaption {{ color: #5a6675; font-size: 13px; margin-top: 8px; }}
    table {{ border-collapse: collapse; width: 100%; background: #fff; border: 1px solid #c9d1db; border-radius: 8px; overflow: hidden; display: block; overflow-x: auto; }}
    th, td {{ padding: 8px 10px; border-bottom: 1px solid #e2e7ee; text-align: left; white-space: nowrap; font-size: 13px; }}
    th {{ background: #eef2f6; }}
    code {{ background: #e9edf2; padding: 1px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
<main>
  <h1>Arrival Latency Outlier Inspection</h1>
  <p>Large step-like movement episodes with final-position arrival <= {max_arrival_latency_s * 1000:.0f} ms and magnitude >= {min_magnitude_deg:.1f} deg. This page is separate from the main report and is intended for ruling out suspicious points in the step-target arrival plot.</p>
  <p>Watch the <code>target_hold_after_s</code> value and the optional <code>next target</code> marker. Many near-zero arrivals occur when the target changes again almost immediately, so the final target is not held long enough for a meaningful response measurement.</p>
  {table}
  {''.join(cards)}
</main>
</body>
</html>
"""


def _outlier_table(rows: list[dict[str, object]]) -> str:
    columns = [
        "axis",
        "episode_idx",
        "magnitude_deg",
        "arrival_latency_s",
        "settling_time_s",
        "target_hold_after_s",
        "initial_target_deg",
        "final_target_deg",
    ]
    head = "".join(f"<th>{column}</th>" for column in columns)
    body = []
    for row in rows:
        body.append(
            "<tr>"
            + "".join(f"<td>{html.escape(_fmt_cell(row[column]))}</td>" for column in columns)
            + "</tr>"
        )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _outlier_description(row: dict[str, object]) -> str:
    arrival_ms = float(row["arrival_latency_s"]) * 1000.0
    hold_ms = float(row["target_hold_after_s"]) * 1000.0
    settling = _fmt_s(_finite_or_none(row["settling_time_s"]))
    return (
        f"{str(row['axis']).capitalize()} episode {int(row['episode_idx'])}: "
        f"{float(row['initial_target_deg']):.2f} deg to {float(row['final_target_deg']):.2f} deg "
        f"({float(row['magnitude_deg']):.2f} deg), arrival {arrival_ms:.1f} ms, "
        f"settling {settling}, target held {hold_ms:.1f} ms after the final target update."
    )


def _motion_disturbance_html(
    rows: list[dict[str, object]],
    requested_examples: int,
    min_vector_deg: float,
    min_target_motion_deg: float,
) -> str:
    cards = []
    for row in rows:
        cards.append(
            "<figure>"
            f'<img src="{html.escape(str(row["file"]))}" alt="motion disturbance event {row["event_idx"]}">'
            f"<figcaption>{html.escape(str(row['description']))}</figcaption>"
            "</figure>"
        )
    table = _motion_disturbance_table(rows)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Motion Disturbance Examples</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #20242a; background: #f6f8fa; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 30px 18px 54px; }}
    h1 {{ margin: 0 0 8px; font-size: 32px; }}
    p {{ color: #5a6675; line-height: 1.45; }}
    figure {{ margin: 22px 0 34px; }}
    img {{ width: 100%; display: block; background: #fff; border: 1px solid #c9d1db; border-radius: 8px; }}
    figcaption {{ color: #5a6675; font-size: 13px; margin-top: 8px; }}
    table {{ border-collapse: collapse; width: 100%; background: #fff; border: 1px solid #c9d1db; border-radius: 8px; overflow: hidden; display: block; overflow-x: auto; }}
    th, td {{ padding: 8px 10px; border-bottom: 1px solid #e2e7ee; text-align: left; white-space: nowrap; font-size: 13px; }}
    th {{ background: #eef2f6; }}
    code {{ background: #e9edf2; padding: 1px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
<main>
  <h1>Motion Disturbance Examples</h1>
  <p>Selected moving-target fire events covering the observed starting pitch/yaw angle space. The requested count was {requested_examples}; {len(rows)} examples met the selection criteria or relaxed fallback.</p>
  <p>Selection starts with non-stable target shots, disturbance vector >= {min_vector_deg:.2f} deg, and target-motion vector >= {min_target_motion_deg:.1f} deg, then uses farthest-point coverage over actual pitch/yaw at fire. The disturbance panels plot <code>actual - target</code> after subtracting the pre-fire baseline, so target motion is largely removed.</p>
  {table}
  {''.join(cards)}
</main>
</body>
</html>
"""


def _motion_disturbance_table(rows: list[dict[str, object]]) -> str:
    columns = [
        "event_idx",
        "pitch_starting_actual_deg",
        "yaw_starting_actual_deg",
        "target_motion_vector_deg",
        "disturbance_vector_abs_deg",
        "pitch_peak_abs_deg",
        "yaw_peak_abs_deg",
        "file",
    ]
    head = "".join(f"<th>{column}</th>" for column in columns)
    body = []
    for row in rows:
        body.append(
            "<tr>"
            + "".join(f"<td>{html.escape(_fmt_cell(row[column]))}</td>" for column in columns)
            + "</tr>"
        )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _motion_disturbance_description(row: dict[str, object]) -> str:
    return (
        f"Event {int(row['event_idx'])}: start pitch "
        f"{float(row['pitch_starting_actual_deg']):.2f} deg, yaw "
        f"{float(row['yaw_starting_actual_deg']):.2f} deg; target motion vector "
        f"{float(row['target_motion_vector_deg']):.2f} deg; disturbance vector "
        f"{float(row['disturbance_vector_abs_deg']):.2f} deg."
    )


def _finite(value: object) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _fmt_cell(value: object) -> str:
    if isinstance(value, float):
        if not np.isfinite(value):
            return ""
        if abs(value) >= 10:
            return f"{value:.2f}"
        if abs(value) >= 1:
            return f"{value:.3f}"
        return f"{value:.4f}"
    return str(value)


def _window_series(stream: ScalarStream, start_s: float, end_s: float) -> tuple[np.ndarray, np.ndarray]:
    mask = (stream.time_s >= start_s) & (stream.time_s <= end_s)
    times = stream.time_s[mask]
    values = stream.value[mask]
    if len(times) <= 1200:
        return times, values
    idx = np.linspace(0, len(times) - 1, 1200).astype(np.int64)
    return times[idx], values[idx]


def _path_data(
    x_values: np.ndarray,
    y_values: np.ndarray,
    sx,
    sy,
) -> str:
    points = []
    for x, y in zip(x_values, y_values):
        if not np.isfinite(x) or not np.isfinite(y):
            continue
        points.append(f"{sx(float(x)):.2f},{sy(float(y)):.2f}")
    if not points:
        return ""
    return "M " + " L ".join(points)


def _legend_items(panels: list[dict[str, object]]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    seen: set[tuple[str, str, bool]] = set()
    for panel in panels:
        for series in panel["series"]:
            label = str(series["label"])
            key = (label, str(series["color"]), bool(series.get("dash")))
            if key in seen:
                continue
            seen.add(key)
            items.append({"label": label, "color": str(series["color"]), "dash": bool(series.get("dash"))})
    return items


def _shot_description(label: str, row: dict[str, object]) -> str:
    return (
        f"Firing response, {label}: event {int(row['event_idx'])}, "
        f"stable_target={int(row['stable_target'])}, "
        f"valid_disturbance_shot={int(row['valid_disturbance_shot'])}, "
        f"pitch peak {float(row['pitch_peak_abs_deg']):.2f} deg, "
        f"yaw peak {float(row['yaw_peak_abs_deg']):.2f} deg."
    )


def _shot_category_label(category: str) -> str:
    labels = {
        "not_stable": "not-stable target",
        "stable_non_trivial": "stable target, non-trivial disturbance",
    }
    return labels.get(category, category.replace("_", " "))


def _axis_color(axis: str) -> str:
    return "#1769aa" if axis == "pitch" else "#c94f2d"


def _finite_or_none(value: object) -> float | None:
    number = float(value)
    return number if np.isfinite(number) else None


def _fmt_s(value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "not observed"
    return f"{value * 1000.0:.0f} ms"


def _ticks(start: float, stop: float, count: int) -> list[float]:
    if count <= 1:
        return [start]
    return [float(value) for value in np.linspace(start, stop, count)]
