# 9mothers Motor Latency Analysis

This repository contains a repeatable analysis workflow for `motor.rrd`, a Rerun recording of turret motor telemetry. The goal is to make the assignment questions answerable from generated tables and reports instead of one-off manual inspection.

## Key Deliverables

- `outputs/summary.md`: written report with methodology, headline results, and tables.
- `outputs/report.html`: visual companion report with scatter plots and summary tables.
- Python source code for the analysis workflow.

## Quick Start

If rebuilding the environment:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

The motor.rrd file is not included in this repository, and should be copied to the root directory before running the analysis.

```bash
.venv/bin/python scripts/analyze_motor.py --input motor.rrd --output outputs
```

Generated files:

- `outputs/summary.md`: written report with methodology, headline results, and tables.
- `outputs/report.html`: visual companion report with scatter plots and summary tables.
- `outputs/overview.csv`: stream sizes, sample rates, and value ranges.
- `outputs/movement_metrics.csv`: one row per detected movement episode.
- `outputs/movement_summary.csv`: broad latency and overshoot summaries over all detected movement episodes.
- `outputs/movement_regression.csv`: simple linear/quadratic checks for magnitude-latency relationships.
- `outputs/shot_metrics.csv`: one row per fire event with stability flags.
- `outputs/shot_summary.csv`: disturbance summaries for all shots and stable-target shots.
- `outputs/analysis_config.json`: exact thresholds used for the run.
- `outputs/exemplars.csv`: automatically selected examples used for the time-series plots.
- `outputs/plots/*.svg`: exemplary time-series plots for small/large movements and firing response categories.
- `outputs/system_id_step_responses.csv`: preserved step-response subset for system identification, with velocity metrics.
- `outputs/system_id.html`: exploratory plots for peak velocity and 90% velocity-rise time.
- `outputs/motion_disturbance_examples.csv`: moving-target fire examples selected across starting pitch/yaw angles.
- `outputs/motion_disturbance.html`: many time-series examples of firing disturbance while the turret is moving.
- `outputs/yaw_10_20_diagnostic_summary.csv`: 2 degree bins for the anomalous yaw 10-20 deg movement range. Used to justify restricting the data considered for Table 1.
- `outputs/yaw_10_20_diagnostics.html`: low/median/high arrival examples from each yaw 10-20 deg sub-bin. Use to justify restricting the data considered for Table 1.
- `outputs/system_id_step_summary.csv`: magnitude-bin summary of the preserved step-response subset.

## What The Workflow Measures

### 1. Motor Response Latency

The target streams contain both discrete step commands and continuously streamed ramp/sweep commands. Measuring every target sample as an independent command would overstate the number of movements and understate context, so the workflow groups same-direction target changes into movement episodes.

For each movement episode it reports:

- `magnitude_deg`: absolute change from the episode's first target to final target.
- `duration_s`: how long the target command took to move from start to final value.
- `arrival_latency_s`: after the final target update, first time the actual position enters tolerance around the final target.
- `settling_time_s`: after the final target update, the confirmed end of the first 50 ms interval where actual position remains inside the tighter settling band.
- `trajectory_lag_s`: during the commanded movement, the target delay from 0 to 400 ms that best aligns the delayed target trajectory to the actual position by RMSE.
- `overshoot_abs_deg`: amount the actual position goes beyond the final target in the movement direction.

For a large streamed sweep, the motor may have already followed most of the move by the final target update, so final-position arrival can be short even for a large movement. `trajectory_lag_s` is often the better control-loop delay estimate for those intervals.

The report also includes a second final-position arrival plot filtered to step-like targets only. A movement is marked `is_step_like_target=1` when the target move is dominated by one jump rather than many smaller updates. This removes ramp/sweep episodes from the arrival-latency view while preserving the original unfiltered plot for comparison. The step-only plot and system-identification subset also exclude final-position arrival below 50 ms, because those near-zero points were ruled out as invalid for this recording.

The system-identification subset is written to `outputs/system_id_step_responses.csv`. It starts from the same step-only, arrival-filtered rows and adds:

- `max_velocity_magnitude_deg_s`: peak absolute finite-difference velocity after the final target update and before the next target update, capped by the response window.
- `velocity_rise_time_90_s`: first time after the command when absolute velocity reaches 90% of that movement's own peak velocity.
- `starting_actual_deg`: actual motor position at the final target update, used for angle-dependent slop checks.

Arrival and settling intentionally use different bands. Arrival uses the broader `max(0.15 deg, 5% of move)` band. Settling uses `max(0.03 deg, 2% of move)` and must hold for 50 ms, so a response that is still visibly drifting through the broader arrival band is not counted as settled.

### 2. Pitch vs Yaw

The generated summaries are split by axis. Use:

- `system_id_step_summary.csv` for the filtered step-response latency, settling, velocity, and overshoot summary used in the main report.
- `movement_summary.csv` only when you need the broad all-episode summary, including ramps and sweeps.
- `movement_metrics.csv` for detailed outlier inspection.

### 3. Shooting Impact

Firing disturbance is computed from tracking error:

```text
tracking error = actual position - target position
disturbance = tracking error - median pre-fire tracking error
```

This isolates mechanical disturbance better than raw position because it removes the commanded position at the event time. The script still flags target stability because many fire events happen while the turret is moving; those are useful operationally but less clean for estimating recoil-like deflection.

Important fields in `shot_metrics.csv`:

- `stable_target`: both axes had less than 0.5 deg target range in the fire window.
- `valid_disturbance_shot`: stable target plus non-trivial disturbance vector.
- `pitch_peak_abs_deg`, `yaw_peak_abs_deg`: peak absolute deflection from pre-fire baseline.
- `pitch_peak_time_s`, `yaw_peak_time_s`: time from fire to peak deflection.
- `pitch_recovery_s`, `yaw_recovery_s`: time from fire until the deviation remains within recovery tolerance for 50 ms.
- `fire_to_muzzle_s`, `fire_to_impact_s`: paired trigger timing deltas.

## Time-Series Exemplars

The report includes SVG time-series plots selected from the metrics:

- Small-angle pitch and yaw movement examples.
- Large-angle pitch and yaw movement examples.
- Firing response when the target is not stable.
- Firing response when the target is stable but the disturbance is trivial.
- Firing response when the target is stable with non-trivial disturbance.

Movement plots show commanded target, actual current, movement start, final target time, arrival, and settling. Firing plots show pitch and yaw target/current before and after `Fire`, with `Muzzle` and `Impact` markers when the recording has paired events in the configured window, plus peak/recovery markers for each axis.

`outputs/motion_disturbance.html` expands the moving-target firing case. It selects non-stable target shots across the observed starting pitch/yaw angle space and adds disturbance panels where the plotted signal is `actual - target` after subtracting the pre-fire baseline. That makes mechanical deflection easier to inspect even when the target and current positions are both moving.

## Tunable Parameters

The defaults are encoded in `AnalysisConfig` in `src/motor_analysis/analysis.py`. The most useful CLI knobs are:

```bash
.venv/bin/python scripts/analyze_motor.py \
  --movement-min-step-deg 0.10 \
  --movement-max-gap-s 0.75 \
  --movement-min-magnitude-deg 1.0 \
  --step-like-max-target-updates 1 \
  --step-like-min-largest-step-fraction 0.80 \
  --response-max-s 2.0 \
  --settling-tolerance-floor-deg 0.03 \
  --settling-tolerance-fraction-of-move 0.02 \
  --shot-stable-target-range-deg 0.50 \
  --motion-disturbance-examples 24 \
  --system-id-min-arrival-latency-s 0.05
```

Re-run the command after changing thresholds. The report records the exact configuration in `outputs/analysis_config.json` and `outputs/summary.md`.

## Recommended Interview Narrative

Start by explaining that the recording is not just a list of clean step commands. The target streams include long moving trajectories, so the analysis intentionally separates final-position arrival/settling from trajectory lag. That makes the system robust to both isolated steps and continuous sweeps.

Then use the generated report to answer:

- How latency changes with movement magnitude: cite the filtered step-response summary table and discuss linearity qualitatively from Figure 2 and `system_id.html`.
- Pitch vs yaw differences: compare median trajectory lag, arrival, settling, and overshoot.
- Shooting impact: use the stable-target, non-trivial-disturbance subset for the clean mechanical disturbance estimate, and mention that all-shot metrics are more confounded by target motion.
