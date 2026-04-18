from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Iterable

import numpy as np

from .analysis import AnalysisConfig
from .system_id import filter_system_id_step_rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=True), encoding="utf-8")


def write_markdown_report(
    path: Path,
    overview_rows: list[dict[str, object]],
    movement_rows: list[dict[str, object]],
    movement_summary: list[dict[str, object]],
    shot_rows: list[dict[str, object]],
    shot_summary: list[dict[str, object]],
    exemplar_rows: list[dict[str, object]],
    config: AnalysisConfig,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table_counter = {"value": 0}
    figure_counter = {"value": 0}

    lines: list[str] = []
    lines.append("# Motor Control Performance Analysis")
    lines.append("")
    lines.append("This report is generated from `motor.rrd` by `scripts/analyze_motor.py`.")
    lines.append("")
    lines.append("## Method Summary")
    lines.append("")
    lines.append(
        "- Scalar streams are extracted from the Rerun recording and aligned to seconds from the first scalar sample."
    )
    lines.append(
        "- Target updates are grouped into same-direction movement episodes, because the recording contains both step-like commands and streamed ramp/sweep commands."
    )
    lines.append(
        "- `is_step_like_target` marks episodes where the target movement is dominated by one jump rather than many small updates."
    )
    lines.append(
        f"- The system-ID step subset keeps step-like targets but excludes final-position arrival below {config.system_id_min_arrival_latency_s * 1000:.0f} ms, because those near-zero cases were ruled out as invalid for this data."
    )
    lines.append(
        "- `arrival_latency_s` is measured after the last target update in an episode: the first current sample within the final target tolerance."
    )
    lines.append(
        "- `settling_time_s` uses a tighter settling band than arrival and marks the end of the configured hold window: the current position must remain inside that band continuously for the full hold time."
    )
    lines.append(
        "- `trajectory_lag_s` estimates control-loop delay during the commanded movement by delaying the target trajectory and choosing the delay with the lowest RMSE to actual position."
    )
    lines.append(
        "- Fire disturbance is measured as current-minus-target error relative to the pre-fire baseline. Stable-target shots are reported separately because moving targets confound pure mechanical deflection."
    )
    lines.append("")
    lines.append("## Key Configuration")
    lines.append("")
    lines.append(
        _markdown_labeled_table(
            _config_rows(config),
            ["parameter", "value"],
            "Analysis thresholds used for this run.",
            table_counter,
        )
    )
    lines.append("")
    lines.append("## Dataset Overview")
    lines.append("")
    lines.append(
        _markdown_labeled_table(
            overview_rows,
            ["path", "samples", "start_s", "end_s", "duration_s", "median_dt_s", "min_value", "max_value"],
            "Extracted scalar streams and basic sampling/value ranges.",
            table_counter,
        )
    )
    lines.append("")
    lines.append("## Movement Response")
    lines.append("")
    lines.extend(_movement_findings(movement_summary))
    lines.extend(_step_latency_findings(movement_rows, config.system_id_min_arrival_latency_s))
    lines.append("")
    lines.append(
        _markdown_labeled_table(
            movement_summary,
            [
                "axis",
                "magnitude_bin",
                "episodes",
                "arrival_n",
                "arrival_median_s",
                "settling_n",
                "settling_median_s",
                "trajectory_lag_n",
                "trajectory_lag_median_s",
                "overshoot_median_deg",
            ],
            "Movement response summary by axis and movement magnitude bin.",
            table_counter,
        )
    )
    lines.append("")
    lines.extend(_movement_summary_n_note(markdown=True))
    lines.append("")
    lines.append("### Movement Exemplars")
    lines.append("")
    lines.extend(_markdown_exemplar_links(exemplar_rows, "movement", figure_counter))
    lines.append("")
    lines.append("## Shooting Impact")
    lines.append("")
    lines.extend(_shot_findings(shot_summary))
    lines.append("")
    lines.append(
        _markdown_labeled_table(
            shot_summary,
            [
                "subset",
                "n",
                "fire_to_muzzle_s_median",
                "fire_to_impact_s_median",
                "pitch_peak_abs_deg_median",
                "pitch_peak_time_s_median",
                "pitch_recovery_s_median",
                "yaw_peak_abs_deg_median",
                "yaw_peak_time_s_median",
                "yaw_recovery_s_median",
                "disturbance_vector_abs_deg_median",
            ],
            "Fire-event disturbance summary for all shots and stable-target subsets.",
            table_counter,
        )
    )
    lines.append("")
    lines.append("### Firing Response Exemplars")
    lines.append("")
    lines.extend(_markdown_exemplar_links(exemplar_rows, "shot", figure_counter))
    lines.append("")
    lines.append("## Output Files")
    lines.append("")
    lines.append("- `overview.csv`: extracted stream sizes, rates, and value ranges.")
    lines.append("- `movement_metrics.csv`: one row per detected movement episode.")
    lines.append("- `movement_summary.csv`: latency and overshoot summaries by axis and movement magnitude.")
    lines.append("- `movement_regression.csv`: simple linear/quadratic checks for magnitude-latency relationships.")
    lines.append("- `shot_metrics.csv`: one row per fire event, including stability flags.")
    lines.append("- `shot_summary.csv`: all-shot and stable-shot disturbance summaries.")
    lines.append("- `exemplars.csv`: selected plot examples and the SVG path for each example.")
    lines.append("- `plots/*.svg`: exemplary time-series plots for movements and firing responses.")
    lines.append("- `motion_disturbance_examples.csv`: moving-target fire examples selected across starting angles.")
    lines.append("- `motion_disturbance.html`: time-series plots for disturbance under motion.")
    lines.append("- `system_id_step_responses.csv`: preserved step-target subset with velocity metrics.")
    lines.append("- `system_id.html`: peak-velocity and velocity-rise diagnostic plots.")
    lines.append("- `report.html`: visual companion report.")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def write_html_report(
    path: Path,
    overview_rows: list[dict[str, object]],
    movement_rows: list[dict[str, object]],
    movement_summary: list[dict[str, object]],
    shot_summary: list[dict[str, object]],
    exemplar_rows: list[dict[str, object]],
    config: AnalysisConfig | None = None,
    observations_text: str = "",
) -> None:
    if config is None:
        config = AnalysisConfig()
    min_latency_ms = config.system_id_min_arrival_latency_s * 1000.0
    figure_counter = {"value": 0}
    table_counter = {"value": 0}
    path.parent.mkdir(parents=True, exist_ok=True)
    arrival_figure = _html_labeled_figure(
        _svg_latency_scatter(movement_rows, "arrival_latency_s", "Final-position arrival latency"),
        "Final-position arrival latency for all detected movement episodes with finite arrival.",
        figure_counter,
    )
    step_arrival_figure = _html_labeled_figure(
        _svg_latency_scatter(
            _system_id_step_rows(movement_rows, config.system_id_min_arrival_latency_s),
            "arrival_latency_s",
            "Final-position arrival latency, step targets only",
            y_max_ms=330.0,
        ),
        f"Step-target final-position arrival after excluding ramp/sweep episodes and arrival below {min_latency_ms:.0f} ms.",
        figure_counter,
    )
    trajectory_figure = _html_labeled_figure(
        _svg_latency_scatter(movement_rows, "trajectory_lag_s", "Trajectory lag during movement"),
        "Trajectory lag estimate across detected movement episodes.",
        figure_counter,
    )
    movement_figures = _html_exemplar_figures(exemplar_rows, "movement", figure_counter)
    shot_figures = _html_exemplar_figures(exemplar_rows, "shot", figure_counter)
    movement_table = _html_labeled_table(
        movement_summary,
        [
            "axis",
            "magnitude_bin",
            "episodes",
            "arrival_n",
            "arrival_median_s",
            "settling_n",
            "settling_median_s",
            "trajectory_lag_n",
            "trajectory_lag_median_s",
            "overshoot_median_deg",
        ],
        "Movement response summary by axis and movement magnitude bin.",
        table_counter,
    )
    shot_table = _html_labeled_table(
        shot_summary,
        [
            "subset",
            "n",
            "fire_to_muzzle_s_median",
            "fire_to_impact_s_median",
            "pitch_peak_abs_deg_median",
            "pitch_peak_time_s_median",
            "pitch_recovery_s_median",
            "yaw_peak_abs_deg_median",
            "yaw_peak_time_s_median",
            "yaw_recovery_s_median",
            "disturbance_vector_abs_deg_median",
        ],
        "Fire-event disturbance summary for all shots and stable-target subsets.",
        table_counter,
    )
    overview_table = _html_labeled_table(
        overview_rows,
        ["path", "samples", "duration_s", "median_dt_s", "min_value", "max_value"],
        "Extracted scalar streams and basic sampling/value ranges.",
        table_counter,
    )
    observations_section = _html_observations_section(observations_text)
    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Motor Control Analysis</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #20242a;
      --muted: #5a6675;
      --line: #c9d1db;
      --pitch: #1769aa;
      --yaw: #c94f2d;
      --bg: #f6f8fa;
      --panel: #ffffff;
    }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
      line-height: 1.45;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 32px 18px 56px;
    }}
    h1, h2, h3 {{
      line-height: 1.15;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 34px;
    }}
    h2 {{
      margin-top: 34px;
      border-top: 1px solid var(--line);
      padding-top: 24px;
    }}
    .lede {{
      color: var(--muted);
      max-width: 860px;
    }}
    .observations {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px 18px;
      margin: 24px 0 28px;
    }}
    .observations h2 {{
      border-top: 0;
      margin: 0 0 12px;
      padding-top: 0;
    }}
    .observations p {{
      margin: 0 0 12px;
    }}
    .observations p:last-child {{
      margin-bottom: 0;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 14px;
      margin: 22px 0;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px 16px;
    }}
    .metric {{
      display: block;
      font-size: 26px;
      font-weight: 700;
    }}
    .label {{
      color: var(--muted);
      font-size: 13px;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      display: block;
      overflow-x: auto;
    }}
    th, td {{
      padding: 8px 10px;
      border-bottom: 1px solid #e2e7ee;
      text-align: left;
      white-space: nowrap;
      font-size: 13px;
    }}
    th {{
      background: #eef2f6;
    }}
    svg {{
      width: 100%;
      height: auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    figure {{
      margin: 18px 0 28px;
    }}
    figure img {{
      width: 100%;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      display: block;
    }}
    figcaption {{
      color: var(--muted);
      font-size: 13px;
      margin-top: 8px;
    }}
    .table-caption {{
      color: var(--muted);
      font-size: 13px;
      margin: 8px 0 20px;
    }}
    .note {{
      color: var(--muted);
      font-size: 14px;
    }}
    code {{
      background: #e9edf2;
      padding: 1px 4px;
      border-radius: 4px;
    }}
  </style>
</head>
<body>
<main>
  <h1>Motor Control Performance Analysis</h1>
  <p class="lede">Generated from <code>motor.rrd</code>. The CSV files next to this report contain the full extracted measurements; this page highlights the patterns needed for the interview assignment.</p>
  {_html_cards(movement_summary, shot_summary)}
  {observations_section}
  <h2>Movement Response</h2>
  <p>{html.escape("The target stream contains both discrete commands and streamed ramps. The analysis groups same-direction target changes into movement episodes, then reports final-position arrival/settling and a trajectory-lag estimate.")}</p>
  {arrival_figure}
  <p class="note">Large moves can have short final-position arrival after the final target update because the motor has already followed most of the streamed movement.</p>
  {step_arrival_figure}
  {trajectory_figure}
  <h3>Movement Exemplars</h3>
  {movement_figures}
  <h3>Movement Summary</h3>
  {movement_table}
  {_html_movement_summary_n_note()}
  <h2>Shooting Impact</h2>
  <p>{html.escape("Fire-event disturbance is measured as the change in tracking error from the pre-fire baseline. The stable-target subset is the cleanest estimate of mechanical deflection because commanded motion is near zero around the trigger.")}</p>
  {shot_table}
  <h3>Firing Response Exemplars</h3>
  {shot_figures}
  <h2>Dataset Overview</h2>
  {overview_table}
</main>
</body>
</html>
"""
    path.write_text(html_text, encoding="utf-8")


def _movement_findings(
    movement_summary: list[dict[str, object]],
) -> list[str]:
    lines: list[str] = []
    pitch_all = _find_row(movement_summary, axis="pitch", magnitude_bin="all")
    yaw_all = _find_row(movement_summary, axis="yaw", magnitude_bin="all")
    if pitch_all and yaw_all:
        lines.append(
            "- Pitch median trajectory lag is "
            f"{_fmt_ms(pitch_all['trajectory_lag_median_s'])}; yaw median trajectory lag is "
            f"{_fmt_ms(yaw_all['trajectory_lag_median_s'])}."
        )
        lines.append(
            "- Pitch median final-position arrival is "
            f"{_fmt_ms(pitch_all['arrival_median_s'])}; yaw median final-position arrival is "
            f"{_fmt_ms(yaw_all['arrival_median_s'])}."
        )
        lines.append(
            "- Pitch median settling time is "
            f"{_fmt_ms(pitch_all['settling_median_s'])}; yaw median settling time is "
            f"{_fmt_ms(yaw_all['settling_median_s'])}."
        )
        lines.append(
            "- Median overshoot is near zero for both axes, but p90 overshoot is "
            f"{_fmt_deg(pitch_all['overshoot_p90_deg'])} for pitch and "
            f"{_fmt_deg(yaw_all['overshoot_p90_deg'])} for yaw."
        )
        lines.append(
            "- Interpretation: yaw looks faster in this recording, while its upper-tail overshoot is larger. "
            "That pattern is consistent with a more aggressive or less damped yaw loop; pitch may also be affected by elevation load, gravity, or different gearing. Treat this as a data-driven hypothesis, not proof of the mechanical cause."
        )
    return lines


def _step_latency_findings(rows: list[dict[str, object]], min_latency_s: float) -> list[str]:
    lines: list[str] = []
    raw_step_rows = [row for row in rows if int(row.get("is_step_like_target", 0)) == 1]
    step_rows = _system_id_step_rows(rows, min_latency_s)
    finite_step_rows = [
        row
        for row in step_rows
        if np.isfinite(float(row.get("arrival_latency_s", np.nan)))
    ]
    lines.append(
        f"- Step-target filtered arrival plot keeps {len(step_rows)} of {len(raw_step_rows)} step-like episodes "
        f"after excluding arrival below {min_latency_s * 1000:.0f} ms; {len(finite_step_rows)} appear as points."
    )
    for axis in ("pitch", "yaw"):
        axis_rows = [
            row
            for row in step_rows
            if row["axis"] == axis and np.isfinite(float(row.get("arrival_latency_s", np.nan)))
        ]
        if not axis_rows:
            continue
        values = np.array([float(row["arrival_latency_s"]) for row in axis_rows], dtype=float)
        lines.append(
            f"- {axis.capitalize()} step-target median final-position arrival is "
            f"{_fmt_ms(float(np.median(values)))} across {len(axis_rows)} finite-arrival episodes."
        )
    return lines


def _shot_findings(shot_summary: list[dict[str, object]]) -> list[str]:
    lines: list[str] = []
    stable = _find_row(shot_summary, subset="stable target shots, non-trivial disturbance")
    all_events = _find_row(shot_summary, subset="all fire events")
    if all_events:
        lines.append(
            "- Across all fire events, median fire-to-muzzle timing is "
            f"{_fmt_ms(all_events['fire_to_muzzle_s_median'])}; median fire-to-impact timing is "
            f"{_fmt_ms(all_events['fire_to_impact_s_median'])}."
        )
    if stable:
        lines.append(
            "- In stable-target shots with non-trivial disturbance, median pitch deflection is "
            f"{_fmt_deg(stable['pitch_peak_abs_deg_median'])} at "
            f"{_fmt_ms(stable['pitch_peak_time_s_median'])}; median yaw deflection is "
            f"{_fmt_deg(stable['yaw_peak_abs_deg_median'])} at "
            f"{_fmt_ms(stable['yaw_peak_time_s_median'])}."
        )
        lines.append(
            "- Median recovery is "
            f"{_fmt_ms(stable['pitch_recovery_s_median'])} for pitch and "
            f"{_fmt_ms(stable['yaw_recovery_s_median'])} for yaw."
        )
        lines.append(
            "- Interpretation: the clean firing disturbance is present in both axes. Pitch is slightly larger and peaks/recoveries are slower; yaw peaks earlier and recovers faster."
        )
        if not np.isfinite(float(stable.get("fire_to_muzzle_s_median", np.nan))):
            lines.append(
                "- The stable-target disturbance subset does not have paired muzzle/impact entries within the pairing window, so trigger-chain timing should be taken from the all-events row."
            )
    return lines


def _html_cards(movement_summary: list[dict[str, object]], shot_summary: list[dict[str, object]]) -> str:
    pitch = _find_row(movement_summary, axis="pitch", magnitude_bin="all")
    yaw = _find_row(movement_summary, axis="yaw", magnitude_bin="all")
    stable = _find_row(shot_summary, subset="stable target shots, non-trivial disturbance")
    cards = []
    if pitch:
        cards.append(("Pitch Trajectory Lag", _fmt_ms(pitch["trajectory_lag_median_s"]), "median across movement episodes"))
    if yaw:
        cards.append(("Yaw Trajectory Lag", _fmt_ms(yaw["trajectory_lag_median_s"]), "median across movement episodes"))
    if stable:
        cards.append(("Stable Shot Deflection", _fmt_deg(stable["disturbance_vector_abs_deg_median"]), "median vector magnitude"))
        cards.append(("Pitch/Yaw Recovery", f"{_fmt_ms(stable['pitch_recovery_s_median'])} / {_fmt_ms(stable['yaw_recovery_s_median'])}", "median stable-shot recovery"))
    return '<section class="grid">' + "".join(
        f'<div class="card"><span class="metric">{html.escape(value)}</span><span class="label">{html.escape(title)} - {html.escape(note)}</span></div>'
        for title, value, note in cards
    ) + "</section>"


def _svg_latency_scatter(
    rows: list[dict[str, object]],
    y_key: str,
    title: str,
    y_max_ms: float | None = None,
) -> str:
    points = [
        row
        for row in rows
        if np.isfinite(float(row.get("magnitude_deg", np.nan))) and np.isfinite(float(row.get(y_key, np.nan)))
    ]
    if not points:
        return "<p>No finite points available.</p>"

    max_points_per_axis = 900
    sampled: list[dict[str, object]] = []
    for axis in ("pitch", "yaw"):
        axis_points = [row for row in points if row["axis"] == axis]
        if len(axis_points) > max_points_per_axis:
            idx = np.linspace(0, len(axis_points) - 1, max_points_per_axis).astype(int)
            sampled.extend(axis_points[i] for i in idx)
        else:
            sampled.extend(axis_points)

    x_values = np.array([float(row["magnitude_deg"]) for row in sampled], dtype=float)
    y_values = np.array([float(row[y_key]) * 1000.0 for row in sampled], dtype=float)
    x_min, x_max = 0.0, max(1.0, float(np.nanpercentile(x_values, 99.5)))
    y_min = 0.0
    y_max = y_max_ms if y_max_ms is not None else max(1.0, float(np.nanpercentile(y_values, 99.0)))
    if y_max <= y_min:
        y_max = y_min + 1.0
    width, height = 920, 360
    left, right, top, bottom = 62, 22, 42, 48
    plot_w = width - left - right
    plot_h = height - top - bottom

    def sx(value: float) -> float:
        return left + (min(value, x_max) - x_min) / (x_max - x_min) * plot_w

    def sy(value: float) -> float:
        return top + plot_h - (min(value, y_max) - y_min) / (y_max - y_min) * plot_h

    circles = []
    colors = {"pitch": "#1769aa", "yaw": "#c94f2d"}
    for row in sampled:
        axis = str(row["axis"])
        x = sx(float(row["magnitude_deg"]))
        y = sy(float(row[y_key]) * 1000.0)
        circles.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.2" fill="{colors[axis]}" opacity="0.38"/>')

    x_ticks = _ticks(x_min, x_max, 6)
    y_ticks = _ticks(y_min, y_max, 5)
    grid = []
    labels = []
    for tick in x_ticks:
        x = sx(tick)
        grid.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{top + plot_h}" stroke="#e5eaf0"/>')
        labels.append(f'<text x="{x:.2f}" y="{height - 16}" text-anchor="middle" font-size="11" fill="#5a6675">{tick:.0f}</text>')
    for tick in y_ticks:
        y = sy(tick)
        grid.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}" stroke="#e5eaf0"/>')
        labels.append(f'<text x="{left - 8}" y="{y + 4:.2f}" text-anchor="end" font-size="11" fill="#5a6675">{tick:.0f}</text>')

    return f"""
<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">
  <text x="{left}" y="24" font-size="17" font-weight="700" fill="#20242a">{html.escape(title)}</text>
  <text x="{left + plot_w - 170}" y="24" font-size="12" fill="#1769aa">pitch</text>
  <text x="{left + plot_w - 105}" y="24" font-size="12" fill="#c94f2d">yaw</text>
  {''.join(grid)}
  <line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#718096"/>
  <line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#718096"/>
  {''.join(circles)}
  {''.join(labels)}
  <text x="{left + plot_w / 2}" y="{height - 2}" text-anchor="middle" font-size="12" fill="#5a6675">movement magnitude (deg)</text>
  <text transform="translate(14 {top + plot_h / 2}) rotate(-90)" text-anchor="middle" font-size="12" fill="#5a6675">latency (ms)</text>
</svg>
"""


def _system_id_step_rows(rows: list[dict[str, object]], min_latency_s: float) -> list[dict[str, object]]:
    return filter_system_id_step_rows(rows, min_latency_s)


def _markdown_table(rows: list[dict[str, object]], columns: list[str]) -> str:
    if not rows:
        return "_No rows._"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(_fmt(row.get(column, "")) for column in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, sep, *body])


def _markdown_labeled_table(
    rows: list[dict[str, object]],
    columns: list[str],
    label: str,
    counter: dict[str, int],
) -> str:
    counter["value"] += 1
    return f"{_markdown_table(rows, columns)}\n\n**Table {counter['value']}.** {label}"


def _html_table(rows: list[dict[str, object]], columns: list[str]) -> str:
    if not rows:
        return "<p>No rows.</p>"
    head = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    body = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(_fmt(row.get(column, '')))}</td>" for column in columns)
        body.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _html_labeled_table(
    rows: list[dict[str, object]],
    columns: list[str],
    label: str,
    counter: dict[str, int],
) -> str:
    counter["value"] += 1
    return (
        _html_table(rows, columns)
        + f'<p class="table-caption"><strong>Table {counter["value"]}.</strong> {html.escape(label)}</p>'
    )


def _html_labeled_figure(svg: str, label: str, counter: dict[str, int]) -> str:
    counter["value"] += 1
    return (
        "<figure>"
        f"{svg}"
        f'<figcaption><strong>Figure {counter["value"]}.</strong> {html.escape(label)}</figcaption>'
        "</figure>"
    )


def _html_observations_section(observations_text: str) -> str:
    paragraphs = [
        paragraph.strip()
        for paragraph in observations_text.split("\n\n")
        if paragraph.strip()
    ]
    if not paragraphs:
        return ""
    body = "".join(f"<p>{html.escape(paragraph)}</p>" for paragraph in paragraphs)
    return f'<section class="observations"><h2>Observations</h2>{body}</section>'


def _markdown_exemplar_links(
    rows: list[dict[str, object]],
    kind: str,
    counter: dict[str, int],
) -> list[str]:
    selected = [row for row in rows if row["kind"] == kind]
    if not selected:
        return ["_No exemplar plots were generated._"]
    lines: list[str] = []
    for row in selected:
        lines.append(f"#### {row['label']}")
        lines.append("")
        lines.append(str(row["description"]))
        lines.append("")
        lines.append(f"![{row['label']}]({row['file']})")
        counter["value"] += 1
        lines.append("")
        lines.append(f"**Figure {counter['value']}.** {row['description']}")
        lines.append("")
    return lines


def _html_exemplar_figures(rows: list[dict[str, object]], kind: str, counter: dict[str, int]) -> str:
    selected = [row for row in rows if row["kind"] == kind]
    if not selected:
        return "<p>No exemplar plots were generated.</p>"
    figures = []
    for row in selected:
        counter["value"] += 1
        figures.append(
            "<figure>"
            f'<img src="{html.escape(str(row["file"]))}" alt="{html.escape(str(row["label"]))}">'
            f'<figcaption><strong>Figure {counter["value"]}.</strong> '
            f"{html.escape(str(row['description']))}</figcaption>"
            "</figure>"
        )
    return "".join(figures)


def _config_rows(config: AnalysisConfig) -> list[dict[str, object]]:
    return [
        {"parameter": key, "value": value}
        for key, value in config.__dict__.items()
    ]


def _movement_summary_n_note(markdown: bool) -> list[str]:
    text = (
        "The `_n` fields are counts of valid finite measurements for that metric within the row's axis/bin, "
        "not additional movement episodes. `arrival_n` counts episodes where the actual position entered the "
        "final-target arrival band before the next target command or response-window cutoff. `settling_n` counts "
        "episodes where the actual position stayed inside the tighter settling band continuously for the configured "
        "50 ms hold window. `trajectory_lag_n` counts episodes with enough samples during the commanded movement to "
        "fit a finite target-delay/RMSE estimate."
    )
    if markdown:
        return [f"_{text}_"]
    return [text]


def _html_movement_summary_n_note() -> str:
    return f'<p class="note">{html.escape(_movement_summary_n_note(markdown=False)[0])}</p>'


def _find_row(rows: Iterable[dict[str, object]], **criteria: object) -> dict[str, object] | None:
    for row in rows:
        if all(row.get(key) == value for key, value in criteria.items()):
            return row
    return None


def _fmt(value: object) -> str:
    if isinstance(value, float):
        if not np.isfinite(value):
            return ""
        if abs(value) >= 1000:
            return f"{value:.1f}"
        if abs(value) >= 10:
            return f"{value:.2f}"
        if abs(value) >= 1:
            return f"{value:.3f}"
        return f"{value:.4f}"
    return str(value)


def _fmt_ms(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(number):
        return ""
    return f"{number * 1000.0:.0f} ms"


def _fmt_deg(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(number):
        return ""
    return f"{number:.2f} deg"


def _ticks(start: float, stop: float, count: int) -> list[float]:
    if count <= 1:
        return [start]
    return [float(value) for value in np.linspace(start, stop, count)]
