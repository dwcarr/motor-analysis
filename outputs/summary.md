# Motor Control Performance Analysis

This report is generated from `motor.rrd` by `scripts/analyze_motor.py`.

## Method Summary

- Scalar streams are extracted from the Rerun recording and aligned to seconds from the first scalar sample.
- Target updates are grouped into same-direction movement episodes, because the recording contains both step-like commands and streamed ramp/sweep commands.
- `is_step_like_target` marks episodes where the target movement is dominated by one jump rather than many small updates.
- `arrival_latency_s` is measured after the last target update in an episode: the first current sample within the final target tolerance.
- `settling_time_s` requires the current position to remain inside tolerance for the configured hold time.
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

## Movement Response

- Pitch median trajectory lag is 70 ms; yaw median trajectory lag is 50 ms.
- Pitch median final-position arrival is 95 ms; yaw median final-position arrival is 65 ms.
- Pitch median settling time is 186 ms; yaw median settling time is 129 ms.
- Median overshoot is near zero for both axes, but p90 overshoot is 0.15 deg for pitch and 0.31 deg for yaw.
- Interpretation: yaw looks faster in this recording, while its upper-tail overshoot is larger. That pattern is consistent with a more aggressive or less damped yaw loop; pitch may also be affected by elevation load, gravity, or different gearing. Treat this as a data-driven hypothesis, not proof of the mechanical cause.
- Pitch arrival latency has low linear fit strength (R2=0.0113); this is evidence against a simple linear magnitude-latency relationship under this episode definition.
- Yaw arrival latency has low linear fit strength (R2=0.0180); this is evidence against a simple linear magnitude-latency relationship under this episode definition.
- Step-target filtered arrival plot keeps 2440 of 5620 movement episodes; 996 have finite final-position arrival and appear as points.
- Pitch step-target median final-position arrival is 184 ms across 443 finite-arrival episodes.
- Yaw step-target median final-position arrival is 83 ms across 553 finite-arrival episodes.

| axis | magnitude_bin | episodes | arrival_n | arrival_median_s | settling_n | settling_median_s | trajectory_lag_n | trajectory_lag_median_s | overshoot_median_deg |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pitch | all | 2843 | 924 | 0.0948 | 727 | 0.1859 | 1835 | 0.0700 | 0.0000 |
| pitch | 0-2 deg | 786 | 209 | 0.0943 | 151 | 0.1810 | 439 | 0.0700 | 0.0000 |
| pitch | 2-5 deg | 1003 | 238 | 0.1266 | 192 | 0.2008 | 687 | 0.0700 | 0.0000 |
| pitch | 5-10 deg | 613 | 227 | 0.0839 | 191 | 0.1812 | 444 | 0.0750 | 0.0000 |
| pitch | 10-20 deg | 324 | 188 | 0.0859 | 160 | 0.2880 | 221 | 0.0700 | 0.0036 |
| pitch | 20+ deg | 117 | 62 | 0.0086 | 33 | 0.1033 | 44 | 0.0750 | 0.0000 |
| yaw | all | 2777 | 1111 | 0.0648 | 670 | 0.1295 | 1822 | 0.0500 | 0.0021 |
| yaw | 0-2 deg | 659 | 317 | 0.0722 | 136 | 0.1250 | 425 | 0.0450 | 0.0307 |
| yaw | 2-5 deg | 785 | 235 | 0.0586 | 121 | 0.1313 | 485 | 0.0500 | 0.0000 |
| yaw | 5-10 deg | 606 | 256 | 0.0592 | 204 | 0.1262 | 410 | 0.0500 | 0.0553 |
| yaw | 10-20 deg | 356 | 119 | 0.0172 | 60 | 0.1191 | 238 | 0.0500 | 0.0000 |
| yaw | 20+ deg | 371 | 184 | 0.0914 | 149 | 0.2079 | 264 | 0.0500 | 0.0014 |

### Movement Exemplars

#### Pitch small angle movement

Pitch small angle movement: 1.00 deg to -1.00 deg (2.00 deg move).

![Pitch small angle movement](plots/movement_pitch_small.svg)

#### Pitch large angle movement

Pitch large angle movement: 28.88 deg to 0.00 deg (28.88 deg move).

![Pitch large angle movement](plots/movement_pitch_large.svg)

#### Yaw small angle movement

Yaw small angle movement: -2.10 deg to -0.00 deg (2.10 deg move).

![Yaw small angle movement](plots/movement_yaw_small.svg)

#### Yaw large angle movement

Yaw large angle movement: 29.02 deg to -0.90 deg (29.92 deg move).

![Yaw large angle movement](plots/movement_yaw_large.svg)


### Linearity Check

| axis | metric | n | linear_slope_per_deg | linear_intercept | linear_r2 | quadratic_r2 |
| --- | --- | --- | --- | --- | --- | --- |
| pitch | arrival_latency_s | 924 | -0.0016 | 0.1286 | 0.0113 | 0.0265 |
| yaw | arrival_latency_s | 1111 | 0.0009 | 0.0573 | 0.0180 | 0.0198 |
| pitch | trajectory_lag_s | 1835 | -0.0011 | 0.0798 | 0.0091 | 0.0106 |
| yaw | trajectory_lag_s | 1822 | 0.0001 | 0.0526 | 0.0010 | 0.0018 |

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

### Firing Response Exemplars

#### Not-stable target

Firing response, not-stable target: event 138, stable_target=0, valid_disturbance_shot=0, pitch peak 3.03 deg, yaw peak 1.87 deg.

![Not-stable target](plots/shot_not_stable.svg)

#### Stable target, trivial disturbance

Firing response, stable target, trivial disturbance: event 38, stable_target=1, valid_disturbance_shot=0, pitch peak 0.00 deg, yaw peak 0.00 deg.

![Stable target, trivial disturbance](plots/shot_stable.svg)

#### Stable target, non-trivial disturbance

Firing response, stable target, non-trivial disturbance: event 77, stable_target=1, valid_disturbance_shot=1, pitch peak 1.83 deg, yaw peak 1.73 deg.

![Stable target, non-trivial disturbance](plots/shot_stable_non_trivial.svg)


## Output Files

- `overview.csv`: extracted stream sizes, rates, and value ranges.
- `movement_metrics.csv`: one row per detected movement episode.
- `movement_summary.csv`: latency and overshoot summaries by axis and movement magnitude.
- `movement_regression.csv`: simple linear/quadratic checks for magnitude-latency relationships.
- `shot_metrics.csv`: one row per fire event, including stability flags.
- `shot_summary.csv`: all-shot and stable-shot disturbance summaries.
- `exemplars.csv`: selected plot examples and the SVG path for each example.
- `plots/*.svg`: exemplary time-series plots for movements and firing responses.
- `report.html`: visual companion report.
