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


def _choose_shots(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {
        "not_stable": _choose_not_stable_shot(rows),
        "stable": _choose_stable_trivial_shot(rows),
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


def _choose_stable_trivial_shot(rows: list[dict[str, object]]) -> dict[str, object]:
    candidates = [
        row
        for row in rows
        if int(row["stable_target"]) == 1 and int(row["valid_disturbance_shot"]) == 0
    ]
    if candidates:
        return min(candidates, key=lambda row: float(row["disturbance_vector_abs_deg"]))
    return min(
        [row for row in rows if int(row["stable_target"]) == 1],
        key=lambda row: float(row["disturbance_vector_abs_deg"]),
    )


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
        window_end = end_s + 0.50

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
        "stable": "stable target, trivial disturbance",
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
