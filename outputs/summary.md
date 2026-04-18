# Motor Control Performance Analysis

This report is generated from `motor.rrd` by `scripts/analyze_motor.py`.

## Method Summary

- Scalar streams are extracted from the Rerun recording and aligned to seconds from the first scalar sample.
- Target updates are grouped into same-direction movement episodes, because the recording contains both step-like commands and streamed ramp/sweep commands.
- `is_step_like_target` marks episodes where the target movement is dominated by one jump rather than many small updates.
- The system-ID step subset keeps step-like targets but excludes final-position arrival below 50 ms, because those near-zero cases were ruled out as invalid for this data.
- `arrival_latency_s` is measured after the last target update in an episode: the first current sample within the final target tolerance.
- `settling_time_s` uses a tighter settling band than arrival and marks the end of the configured hold window: the current position must remain inside that band continuously for the full hold time.
- `trajectory_lag_s` estimates control-loop delay during the commanded movement by delaying the target trajectory and choosing the delay with the lowest RMSE to actual position.
- Fire disturbance is measured as current-minus-target error relative to the pre-fire baseline. Stable-target shots are reported separately because moving targets confound pure mechanical deflection.

## Key Configuration

| parameter | value |
| --- | --- |
| movement_min_step_deg | 0.1000 |
| movement_max_gap_s | 0.7500 |
| movement_min_magnitude_deg | 1.000 |
| step_like_max_target_updates | 1 |
| step_like_min_largest_step_fraction | 0.8000 |
| response_max_s | 2.000 |
| settle_hold_s | 0.0500 |
| tolerance_floor_deg | 0.1500 |
| tolerance_fraction_of_move | 0.0500 |
| settling_tolerance_floor_deg | 0.0300 |
| settling_tolerance_fraction_of_move | 0.0200 |
| lag_max_s | 0.4000 |
| lag_step_s | 0.0050 |
| lag_max_samples | 800 |
| shot_pre_s | 0.1200 |
| shot_post_s | 0.5000 |
| shot_baseline_ignore_s | 0.0200 |
| shot_stable_target_range_deg | 0.5000 |
| shot_recovery_floor_deg | 0.0500 |
| shot_recovery_fraction_of_peak | 0.2000 |
| shot_valid_vector_min_deg | 0.2500 |
| trigger_pair_max_s | 1.000 |
| system_id_min_arrival_latency_s | 0.0500 |

**Table 1.** Analysis thresholds used for this run.

## Dataset Overview

| path | samples | start_s | end_s | duration_s | median_dt_s | min_value | max_value |
| --- | --- | --- | --- | --- | --- | --- | --- |
| /motors/position/pitch/current | 965015 | 0.0000 | 10287.2 | 10287.2 | 0.0101 | -13.99 | 37.05 |
| /motors/position/pitch/target | 56885 | 16.25 | 10108.2 | 10091.9 | 0.0175 | -14.00 | 37.00 |
| /motors/position/yaw/current | 989091 | 0.0007 | 10287.2 | 10287.2 | 0.0100 | -37.00 | 57.16 |
| /motors/position/yaw/target | 56885 | 16.25 | 10108.2 | 10091.9 | 0.0175 | -37.00 | 57.00 |
| /trigger/fire | 375 | 446.82 | 10104.5 | 9657.6 | 7.611 | 1.000 | 1.000 |
| /trigger/impact | 364 | 446.94 | 10104.6 | 9657.6 | 7.371 | 1.000 | 1.000 |
| /trigger/muzzle | 364 | 446.86 | 10104.5 | 9657.6 | 7.368 | 1.000 | 1.000 |

**Table 2.** Extracted scalar streams and basic sampling/value ranges.

## Movement Response

- Pitch median trajectory lag is 70 ms; yaw median trajectory lag is 50 ms.
- Pitch median final-position arrival is 95 ms; yaw median final-position arrival is 65 ms.
- Pitch median settling time is 288 ms; yaw median settling time is 252 ms.
- Median overshoot is near zero for both axes, but p90 overshoot is 0.15 deg for pitch and 0.31 deg for yaw.
- Interpretation: yaw looks faster in this recording, while its upper-tail overshoot is larger. That pattern is consistent with a more aggressive or less damped yaw loop; pitch may also be affected by elevation load, gravity, or different gearing. Treat this as a data-driven hypothesis, not proof of the mechanical cause.
- Step-target filtered arrival plot keeps 693 of 2440 step-like episodes after excluding arrival below 50 ms; 693 appear as points.
- Pitch step-target median final-position arrival is 227 ms across 287 finite-arrival episodes.
- Yaw step-target median final-position arrival is 97 ms across 406 finite-arrival episodes.

| axis | magnitude_bin | episodes | arrival_n | arrival_median_s | settling_n | settling_median_s | trajectory_lag_n | trajectory_lag_median_s | overshoot_median_deg |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pitch | all | 2843 | 924 | 0.0948 | 580 | 0.2883 | 1835 | 0.0700 | 0.0000 |
| pitch | 0-2 deg | 786 | 209 | 0.0943 | 84 | 0.3117 | 439 | 0.0700 | 0.0000 |
| pitch | 2-5 deg | 1003 | 238 | 0.1266 | 132 | 0.2787 | 687 | 0.0700 | 0.0000 |
| pitch | 5-10 deg | 613 | 227 | 0.0839 | 176 | 0.2528 | 444 | 0.0750 | 0.0000 |
| pitch | 10-20 deg | 324 | 188 | 0.0859 | 158 | 0.3476 | 221 | 0.0700 | 0.0036 |
| pitch | 20+ deg | 117 | 62 | 0.0086 | 30 | 0.1423 | 44 | 0.0750 | 0.0000 |
| yaw | all | 2777 | 1111 | 0.0648 | 532 | 0.2525 | 1822 | 0.0500 | 0.0021 |
| yaw | 0-2 deg | 659 | 317 | 0.0722 | 68 | 0.2531 | 425 | 0.0450 | 0.0307 |
| yaw | 2-5 deg | 785 | 235 | 0.0586 | 79 | 0.2444 | 485 | 0.0500 | 0.0000 |
| yaw | 5-10 deg | 606 | 256 | 0.0592 | 187 | 0.2327 | 410 | 0.0500 | 0.0553 |
| yaw | 10-20 deg | 356 | 119 | 0.0172 | 58 | 0.1404 | 238 | 0.0500 | 0.0000 |
| yaw | 20+ deg | 371 | 184 | 0.0914 | 140 | 0.2991 | 264 | 0.0500 | 0.0014 |

**Table 3.** Movement response summary by axis and movement magnitude bin.

_The `_n` fields are counts of valid finite measurements for that metric within the row's axis/bin, not additional movement episodes. `arrival_n` counts episodes where the actual position entered the final-target arrival band before the next target command or response-window cutoff. `settling_n` counts episodes where the actual position stayed inside the tighter settling band continuously for the configured 50 ms hold window. `trajectory_lag_n` counts episodes with enough samples during the commanded movement to fit a finite target-delay/RMSE estimate._

### Movement Exemplars

#### Pitch small angle movement

Pitch small angle movement: 1.00 deg to -1.00 deg (2.00 deg move).

![Pitch small angle movement](plots/movement_pitch_small.svg)

**Figure 1.** Pitch small angle movement: 1.00 deg to -1.00 deg (2.00 deg move).

#### Pitch large angle movement

Pitch large angle movement: 28.88 deg to 0.00 deg (28.88 deg move).

![Pitch large angle movement](plots/movement_pitch_large.svg)

**Figure 2.** Pitch large angle movement: 28.88 deg to 0.00 deg (28.88 deg move).

#### Yaw small angle movement

Yaw small angle movement: -2.10 deg to -0.00 deg (2.10 deg move).

![Yaw small angle movement](plots/movement_yaw_small.svg)

**Figure 3.** Yaw small angle movement: -2.10 deg to -0.00 deg (2.10 deg move).

#### Yaw large angle movement

Yaw large angle movement: 29.02 deg to -0.90 deg (29.92 deg move).

![Yaw large angle movement](plots/movement_yaw_large.svg)

**Figure 4.** Yaw large angle movement: 29.02 deg to -0.90 deg (29.92 deg move).


## Shooting Impact

- Across all fire events, median fire-to-muzzle timing is 41 ms; median fire-to-impact timing is 157 ms.
- In stable-target shots with non-trivial disturbance, median pitch deflection is 1.82 deg at 139 ms; median yaw deflection is 1.71 deg at 72 ms.
- Median recovery is 263 ms for pitch and 175 ms for yaw.
- Interpretation: the clean firing disturbance is present in both axes. Pitch is slightly larger and peaks/recoveries are slower; yaw peaks earlier and recovers faster.
- The stable-target disturbance subset does not have paired muzzle/impact entries within the pairing window, so trigger-chain timing should be taken from the all-events row.

| subset | n | fire_to_muzzle_s_median | fire_to_impact_s_median | pitch_peak_abs_deg_median | pitch_peak_time_s_median | pitch_recovery_s_median | yaw_peak_abs_deg_median | yaw_peak_time_s_median | yaw_recovery_s_median | disturbance_vector_abs_deg_median |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all fire events | 375 | 0.0405 | 0.1566 | 1.948 | 0.1894 | 0.3002 | 1.733 | 0.1742 | 0.2079 | 2.723 |
| stable target shots | 11 |  |  | 1.807 | 0.1386 | 0.2624 | 1.694 | 0.0711 | 0.1726 | 2.478 |
| stable target shots, non-trivial disturbance | 10 |  |  | 1.816 | 0.1390 | 0.2630 | 1.711 | 0.0717 | 0.1746 | 2.498 |

**Table 4.** Fire-event disturbance summary for all shots and stable-target subsets.

### Firing Response Exemplars

#### Not-stable target

Firing response, not-stable target: event 138, stable_target=0, valid_disturbance_shot=0, pitch peak 3.03 deg, yaw peak 1.87 deg.

![Not-stable target](plots/shot_not_stable.svg)

**Figure 5.** Firing response, not-stable target: event 138, stable_target=0, valid_disturbance_shot=0, pitch peak 3.03 deg, yaw peak 1.87 deg.

#### Stable target, non-trivial disturbance

Firing response, stable target, non-trivial disturbance: event 77, stable_target=1, valid_disturbance_shot=1, pitch peak 1.83 deg, yaw peak 1.73 deg.

![Stable target, non-trivial disturbance](plots/shot_stable_non_trivial.svg)

**Figure 6.** Firing response, stable target, non-trivial disturbance: event 77, stable_target=1, valid_disturbance_shot=1, pitch peak 1.83 deg, yaw peak 1.73 deg.


## Output Files

- `overview.csv`: extracted stream sizes, rates, and value ranges.
- `movement_metrics.csv`: one row per detected movement episode.
- `movement_summary.csv`: latency and overshoot summaries by axis and movement magnitude.
- `movement_regression.csv`: simple linear/quadratic checks for magnitude-latency relationships.
- `shot_metrics.csv`: one row per fire event, including stability flags.
- `shot_summary.csv`: all-shot and stable-shot disturbance summaries.
- `exemplars.csv`: selected plot examples and the SVG path for each example.
- `plots/*.svg`: exemplary time-series plots for movements and firing responses.
- `motion_disturbance_examples.csv`: moving-target fire examples selected across starting angles.
- `motion_disturbance.html`: time-series plots for disturbance under motion.
- `system_id_step_responses.csv`: preserved step-target subset with velocity metrics.
- `system_id.html`: peak-velocity and velocity-rise diagnostic plots.
- `report.html`: visual companion report.
