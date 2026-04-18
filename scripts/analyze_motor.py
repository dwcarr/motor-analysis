#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from motor_analysis import AnalysisConfig, analyze_movements, analyze_shots, build_overview, load_scalar_streams
from motor_analysis.analysis import regression_summary
from motor_analysis.plots import (
    write_exemplar_plots,
    write_motion_disturbance_page,
    write_outlier_inspection_page,
)
from motor_analysis.report import write_csv, write_html_report, write_json, write_markdown_report
from motor_analysis.system_id import build_system_id_step_response_rows, write_system_id_page


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract motor telemetry from a Rerun .rrd file and generate analysis outputs.",
    )
    parser.add_argument("--input", default="motor.rrd", help="Path to the Rerun recording.")
    parser.add_argument("--output", default="outputs", help="Directory for CSV and report outputs.")
    parser.add_argument("--movement-min-step-deg", type=float, default=0.10)
    parser.add_argument("--movement-max-gap-s", type=float, default=0.75)
    parser.add_argument("--movement-min-magnitude-deg", type=float, default=1.0)
    parser.add_argument("--step-like-max-target-updates", type=int, default=1)
    parser.add_argument("--step-like-min-largest-step-fraction", type=float, default=0.80)
    parser.add_argument("--response-max-s", type=float, default=2.0)
    parser.add_argument("--settling-tolerance-floor-deg", type=float, default=0.03)
    parser.add_argument("--settling-tolerance-fraction-of-move", type=float, default=0.02)
    parser.add_argument("--shot-stable-target-range-deg", type=float, default=0.50)
    parser.add_argument("--outlier-min-magnitude-deg", type=float, default=8.0)
    parser.add_argument("--outlier-max-arrival-latency-s", type=float, default=0.02)
    parser.add_argument("--outlier-examples-per-axis", type=int, default=6)
    parser.add_argument("--motion-disturbance-examples", type=int, default=24)
    parser.add_argument("--motion-disturbance-min-vector-deg", type=float, default=0.25)
    parser.add_argument("--motion-disturbance-min-target-motion-deg", type=float, default=1.0)
    parser.add_argument("--system-id-min-arrival-latency-s", type=float, default=0.05)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output)

    config = AnalysisConfig(
        movement_min_step_deg=args.movement_min_step_deg,
        movement_max_gap_s=args.movement_max_gap_s,
        movement_min_magnitude_deg=args.movement_min_magnitude_deg,
        step_like_max_target_updates=args.step_like_max_target_updates,
        step_like_min_largest_step_fraction=args.step_like_min_largest_step_fraction,
        response_max_s=args.response_max_s,
        settling_tolerance_floor_deg=args.settling_tolerance_floor_deg,
        settling_tolerance_fraction_of_move=args.settling_tolerance_fraction_of_move,
        shot_stable_target_range_deg=args.shot_stable_target_range_deg,
        system_id_min_arrival_latency_s=args.system_id_min_arrival_latency_s,
    )

    streams = load_scalar_streams(input_path)
    overview_rows = build_overview(streams)
    movement_rows, movement_summary = analyze_movements(streams, config)
    movement_regression = regression_summary(movement_rows, "arrival_latency_s") + regression_summary(
        movement_rows, "trajectory_lag_s"
    )
    shot_rows, shot_summary = analyze_shots(streams, config)

    output_dir.mkdir(parents=True, exist_ok=True)
    exemplar_rows = write_exemplar_plots(output_dir, streams, movement_rows, shot_rows, config)
    outlier_rows = write_outlier_inspection_page(
        output_dir,
        streams,
        movement_rows,
        config,
        min_magnitude_deg=args.outlier_min_magnitude_deg,
        max_arrival_latency_s=args.outlier_max_arrival_latency_s,
        per_axis=args.outlier_examples_per_axis,
    )
    motion_disturbance_rows = write_motion_disturbance_page(
        output_dir,
        streams,
        shot_rows,
        config,
        examples=args.motion_disturbance_examples,
        min_vector_deg=args.motion_disturbance_min_vector_deg,
        min_target_motion_deg=args.motion_disturbance_min_target_motion_deg,
    )
    system_id_rows = build_system_id_step_response_rows(streams, movement_rows, config)
    write_system_id_page(output_dir, system_id_rows, config)
    write_csv(output_dir / "overview.csv", overview_rows)
    write_csv(output_dir / "movement_metrics.csv", movement_rows)
    write_csv(output_dir / "movement_summary.csv", movement_summary)
    write_csv(output_dir / "movement_regression.csv", movement_regression)
    write_csv(output_dir / "shot_metrics.csv", shot_rows)
    write_csv(output_dir / "shot_summary.csv", shot_summary)
    write_csv(output_dir / "exemplars.csv", exemplar_rows)
    write_csv(output_dir / "outlier_inspection.csv", outlier_rows)
    write_csv(output_dir / "motion_disturbance_examples.csv", motion_disturbance_rows)
    write_csv(output_dir / "system_id_step_responses.csv", system_id_rows)
    write_json(output_dir / "analysis_config.json", config.__dict__)
    write_markdown_report(
        output_dir / "summary.md",
        overview_rows,
        movement_rows,
        movement_summary,
        shot_rows,
        shot_summary,
        exemplar_rows,
        config,
    )
    write_html_report(
        output_dir / "report.html",
        overview_rows,
        movement_rows,
        movement_summary,
        shot_summary,
        exemplar_rows,
        config,
        _read_optional_text(ROOT / "observations.md"),
    )

    print(f"Wrote analysis outputs to {output_dir.resolve()}")
    print(f"Movement episodes: {len(movement_rows)}")
    print(f"Fire events: {len(shot_rows)}")
    print(f"Exemplar plots: {len(exemplar_rows)}")
    print(f"Outlier examples: {len(outlier_rows)}")
    print(f"Motion disturbance examples: {len(motion_disturbance_rows)}")
    print(f"System ID step responses: {len(system_id_rows)}")
    print(f"Summary: {(output_dir / 'summary.md').resolve()}")
    print(f"HTML report: {(output_dir / 'report.html').resolve()}")
    print(f"Outlier page: {(output_dir / 'outlier_inspection.html').resolve()}")
    print(f"Motion disturbance page: {(output_dir / 'motion_disturbance.html').resolve()}")
    print(f"System ID page: {(output_dir / 'system_id.html').resolve()}")
    return 0


def _read_optional_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


if __name__ == "__main__":
    raise SystemExit(main())
