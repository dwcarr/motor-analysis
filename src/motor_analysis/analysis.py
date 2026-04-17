from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Iterable

import numpy as np

from .rrd import ScalarStream


AXES = ("pitch", "yaw")
TRIGGERS = ("fire", "muzzle", "impact")


@dataclass(frozen=True)
class AnalysisConfig:
    """
    Tunable thresholds for the analysis.

    The defaults are intentionally conservative for this recording:
    - movement episodes group same-direction target changes into one command
      episode, because the target stream contains both steps and ramps.
    - final-position metrics are only measured after an episode's final target.
    - shot disturbance metrics are reported for every fire event, then filtered
      to stable-target shots for the cleaner mechanical-disturbance estimate.
    """

    movement_min_step_deg: float = 0.10
    movement_max_gap_s: float = 0.75
    movement_min_magnitude_deg: float = 1.0
    step_like_max_target_updates: int = 1
    step_like_min_largest_step_fraction: float = 0.80
    response_max_s: float = 2.0
    settle_hold_s: float = 0.05
    tolerance_floor_deg: float = 0.15
    tolerance_fraction_of_move: float = 0.05
    lag_max_s: float = 0.40
    lag_step_s: float = 0.005
    lag_max_samples: int = 800
    shot_pre_s: float = 0.12
    shot_post_s: float = 0.50
    shot_baseline_ignore_s: float = 0.02
    shot_stable_target_range_deg: float = 0.50
    shot_recovery_floor_deg: float = 0.05
    shot_recovery_fraction_of_peak: float = 0.20
    shot_valid_vector_min_deg: float = 0.25
    trigger_pair_max_s: float = 1.0


def build_overview(streams: dict[str, ScalarStream]) -> list[dict[str, float | int | str]]:
    """Summarize each scalar stream for quick recording sanity checks."""

    rows: list[dict[str, float | int | str]] = []
    for path, stream in sorted(streams.items()):
        dt = np.diff(stream.time_s)
        rows.append(
            {
                "path": path,
                "samples": int(len(stream.value)),
                "start_s": float(stream.time_s[0]),
                "end_s": float(stream.time_s[-1]),
                "duration_s": float(stream.duration_s),
                "median_dt_s": float(np.median(dt)) if len(dt) else np.nan,
                "p99_dt_s": float(np.percentile(dt, 99)) if len(dt) else np.nan,
                "min_value": float(np.nanmin(stream.value)),
                "max_value": float(np.nanmax(stream.value)),
            }
        )
    return rows


def analyze_movements(
    streams: dict[str, ScalarStream],
    config: AnalysisConfig,
) -> tuple[list[dict[str, float | int | str]], list[dict[str, float | int | str]]]:
    """Measure movement-response metrics and aggregate them by magnitude bin."""

    movement_rows: list[dict[str, float | int | str]] = []
    for axis in AXES:
        current = streams[_motor_path(axis, "current")]
        target = streams[_motor_path(axis, "target")]
        episodes = _detect_movement_episodes(target.time_s, target.value, config)

        for episode_idx, episode in enumerate(episodes):
            next_start_s = (
                target.time_s[episodes[episode_idx + 1]["start_idx"]]
                if episode_idx + 1 < len(episodes)
                else min(current.time_s[-1], target.time_s[episode["last_idx"]] + config.response_max_s)
            )
            movement_rows.append(
                _measure_episode(axis, episode_idx, episode, next_start_s, current, target, config)
            )

    return movement_rows, summarize_movements(movement_rows)


def analyze_shots(
    streams: dict[str, ScalarStream],
    config: AnalysisConfig,
) -> tuple[list[dict[str, float | int | str]], list[dict[str, float | int | str]]]:
    """Measure fire-event disturbances and aggregate all/stable subsets."""

    fire = streams["/trigger/fire"].time_s
    muzzle = streams.get("/trigger/muzzle")
    impact = streams.get("/trigger/impact")
    shot_rows: list[dict[str, float | int | str]] = []

    for event_idx, fire_time_s in enumerate(fire):
        row: dict[str, float | int | str] = {
            "event_idx": event_idx,
            "fire_time_s": float(fire_time_s),
            "fire_to_muzzle_s": _next_delta_s(fire_time_s, muzzle.time_s if muzzle else None, config),
            "fire_to_impact_s": _next_delta_s(fire_time_s, impact.time_s if impact else None, config),
        }

        stable_target = True
        for axis in AXES:
            axis_metrics = _measure_shot_axis(axis, fire_time_s, streams, config)
            row.update(axis_metrics)
            stable_target = stable_target and bool(axis_metrics[f"{axis}_target_stable"])

        pitch_peak = float(row.get("pitch_peak_abs_deg", np.nan))
        yaw_peak = float(row.get("yaw_peak_abs_deg", np.nan))
        vector_peak = sqrt(pitch_peak * pitch_peak + yaw_peak * yaw_peak)
        row["disturbance_vector_abs_deg"] = vector_peak
        row["stable_target"] = int(stable_target)
        row["valid_disturbance_shot"] = int(
            stable_target and np.isfinite(vector_peak) and vector_peak >= config.shot_valid_vector_min_deg
        )
        shot_rows.append(row)

    return shot_rows, summarize_shots(shot_rows)


def summarize_movements(rows: list[dict[str, float | int | str]]) -> list[dict[str, float | int | str]]:
    bins = [
        (0.0, 2.0, "0-2 deg"),
        (2.0, 5.0, "2-5 deg"),
        (5.0, 10.0, "5-10 deg"),
        (10.0, 20.0, "10-20 deg"),
        (20.0, float("inf"), "20+ deg"),
    ]
    summary: list[dict[str, float | int | str]] = []

    for axis in AXES:
        axis_rows = [row for row in rows if row["axis"] == axis]
        summary.append(_movement_summary_row(axis, "all", axis_rows))
        for lo, hi, label in bins:
            bin_rows = [
                row for row in axis_rows if lo <= float(row["magnitude_deg"]) < hi
            ]
            summary.append(_movement_summary_row(axis, label, bin_rows))

    return summary


def summarize_shots(rows: list[dict[str, float | int | str]]) -> list[dict[str, float | int | str]]:
    subsets = [
        ("all fire events", rows),
        ("stable target shots", [row for row in rows if int(row["stable_target"]) == 1]),
        (
            "stable target shots, non-trivial disturbance",
            [row for row in rows if int(row["valid_disturbance_shot"]) == 1],
        ),
    ]

    out: list[dict[str, float | int | str]] = []
    for label, subset in subsets:
        summary: dict[str, float | int | str] = {"subset": label, "n": len(subset)}
        for key in [
            "fire_to_muzzle_s",
            "fire_to_impact_s",
            "pitch_peak_abs_deg",
            "pitch_peak_time_s",
            "pitch_recovery_s",
            "yaw_peak_abs_deg",
            "yaw_peak_time_s",
            "yaw_recovery_s",
            "disturbance_vector_abs_deg",
        ]:
            values = _finite_values(subset, key)
            summary[f"{key}_median"] = _safe_percentile(values, 50)
            summary[f"{key}_p90"] = _safe_percentile(values, 90)
        out.append(summary)
    return out


def regression_summary(
    rows: list[dict[str, float | int | str]],
    y_key: str,
) -> list[dict[str, float | int | str]]:
    """Return linear/quadratic fits of a movement metric against move magnitude."""

    out: list[dict[str, float | int | str]] = []
    for axis in AXES:
        axis_rows = [row for row in rows if row["axis"] == axis]
        x = np.array([float(row["magnitude_deg"]) for row in axis_rows], dtype=np.float64)
        y = np.array([float(row[y_key]) for row in axis_rows], dtype=np.float64)
        ok = np.isfinite(x) & np.isfinite(y)
        if ok.sum() < 5:
            out.append(
                {
                    "axis": axis,
                    "metric": y_key,
                    "n": int(ok.sum()),
                    "linear_slope_per_deg": np.nan,
                    "linear_intercept": np.nan,
                    "linear_r2": np.nan,
                    "quadratic_r2": np.nan,
                }
            )
            continue

        linear = np.polyfit(x[ok], y[ok], 1)
        quadratic = np.polyfit(x[ok], y[ok], 2)
        out.append(
            {
                "axis": axis,
                "metric": y_key,
                "n": int(ok.sum()),
                "linear_slope_per_deg": float(linear[0]),
                "linear_intercept": float(linear[1]),
                "linear_r2": float(_r2(y[ok], np.polyval(linear, x[ok]))),
                "quadratic_r2": float(_r2(y[ok], np.polyval(quadratic, x[ok]))),
            }
        )
    return out


def zero_order_hold(sample_t: np.ndarray, sample_v: np.ndarray, query_t: np.ndarray) -> np.ndarray:
    """Sample the most recent target value at each query timestamp."""

    idx = np.searchsorted(sample_t, query_t, side="right") - 1
    idx = np.clip(idx, 0, len(sample_v) - 1)
    return sample_v[idx]


def _detect_movement_episodes(
    target_t: np.ndarray,
    target_v: np.ndarray,
    config: AnalysisConfig,
) -> list[dict[str, int]]:
    """
    Group same-direction target changes into movement episodes.

    A naive per-sample step detector is misleading here because large commanded
    moves are often represented as many small target updates. Grouping by sign
    preserves both true steps and ramp/sweep commands.
    """

    delta = np.diff(target_v)
    change_indices = np.flatnonzero(np.abs(delta) >= config.movement_min_step_deg) + 1
    episodes: list[dict[str, int]] = []
    current: dict[str, int] | None = None

    for idx in change_indices:
        sign = 1 if delta[idx - 1] > 0 else -1
        if current is None:
            current = {"start_idx": int(idx - 1), "last_idx": int(idx), "sign": sign}
            continue

        gap_s = target_t[idx] - target_t[current["last_idx"]]
        if sign == current["sign"] and gap_s <= config.movement_max_gap_s:
            current["last_idx"] = int(idx)
            continue

        _append_episode_if_large_enough(episodes, current, target_t, target_v, config)
        current = {"start_idx": int(idx - 1), "last_idx": int(idx), "sign": sign}

    if current is not None:
        _append_episode_if_large_enough(episodes, current, target_t, target_v, config)

    return episodes


def _append_episode_if_large_enough(
    episodes: list[dict[str, int]],
    episode: dict[str, int],
    target_t: np.ndarray,
    target_v: np.ndarray,
    config: AnalysisConfig,
) -> None:
    start_idx = episode["start_idx"]
    last_idx = episode["last_idx"]
    magnitude = abs(target_v[last_idx] - target_v[start_idx])
    duration_s = target_t[last_idx] - target_t[start_idx]
    if magnitude >= config.movement_min_magnitude_deg and duration_s > 0.0:
        episodes.append(episode)


def _measure_episode(
    axis: str,
    episode_idx: int,
    episode: dict[str, int],
    next_start_s: float,
    current: ScalarStream,
    target: ScalarStream,
    config: AnalysisConfig,
) -> dict[str, float | int | str]:
    start_idx = episode["start_idx"]
    last_idx = episode["last_idx"]
    start_s = float(target.time_s[start_idx])
    end_s = float(target.time_s[last_idx])
    initial_target = float(target.value[start_idx])
    final_target = float(target.value[last_idx])
    delta_deg = final_target - initial_target
    direction = 1.0 if delta_deg > 0.0 else -1.0
    magnitude = abs(delta_deg)
    shape = _target_shape_metrics(target.time_s, target.value, start_idx, last_idx, magnitude, config)
    tolerance = max(config.tolerance_floor_deg, config.tolerance_fraction_of_move * magnitude)
    post_end_s = min(end_s + config.response_max_s, next_start_s)

    arrival_latency_s = np.nan
    settling_time_s = np.nan
    overshoot_signed_deg = np.nan
    overshoot_abs_deg = np.nan

    post_mask = (current.time_s >= end_s) & (current.time_s <= post_end_s)
    post_t = current.time_s[post_mask]
    post_v = current.value[post_mask]

    if len(post_t):
        if direction > 0.0:
            reached = post_v >= final_target - tolerance
            overshoot_abs_deg = max(0.0, float(np.max(post_v - final_target)))
            overshoot_signed_deg = overshoot_abs_deg
        else:
            reached = post_v <= final_target + tolerance
            overshoot_abs_deg = max(0.0, float(np.max(final_target - post_v)))
            overshoot_signed_deg = -overshoot_abs_deg

        if np.any(reached):
            arrival_latency_s = float(post_t[int(np.argmax(reached))] - end_s)

        abs_error = np.abs(post_v - final_target)
        settling_time_s = _first_stable_time(
            post_t,
            abs_error,
            tolerance,
            config.settle_hold_s,
            end_s,
        )

    lag_s, lag_rmse_deg = _best_trajectory_lag(
        start_s,
        end_s,
        current,
        target,
        config,
    )

    return {
        "axis": axis,
        "episode_idx": episode_idx,
        "start_time_s": start_s,
        "end_time_s": end_s,
        "duration_s": end_s - start_s,
        "target_hold_after_s": max(0.0, float(next_start_s - end_s)),
        "initial_target_deg": initial_target,
        "final_target_deg": final_target,
        "delta_deg": delta_deg,
        "magnitude_deg": magnitude,
        "target_update_count": shape["target_update_count"],
        "target_largest_step_deg": shape["target_largest_step_deg"],
        "target_largest_step_fraction": shape["target_largest_step_fraction"],
        "is_step_like_target": shape["is_step_like_target"],
        "tolerance_deg": tolerance,
        "arrival_latency_s": arrival_latency_s,
        "settling_time_s": settling_time_s,
        "overshoot_signed_deg": overshoot_signed_deg,
        "overshoot_abs_deg": overshoot_abs_deg,
        "trajectory_lag_s": lag_s,
        "trajectory_lag_rmse_deg": lag_rmse_deg,
    }


def _target_shape_metrics(
    target_t: np.ndarray,
    target_v: np.ndarray,
    start_idx: int,
    last_idx: int,
    magnitude: float,
    config: AnalysisConfig,
) -> dict[str, float | int]:
    deltas = np.abs(np.diff(target_v[start_idx : last_idx + 1]))
    changed = deltas[deltas >= config.movement_min_step_deg]
    largest = float(np.max(changed)) if len(changed) else 0.0
    fraction = largest / magnitude if magnitude > 0.0 else np.nan
    is_step_like = (
        len(changed) <= config.step_like_max_target_updates
        and np.isfinite(fraction)
        and fraction >= config.step_like_min_largest_step_fraction
    )
    return {
        "target_update_count": int(len(changed)),
        "target_largest_step_deg": largest,
        "target_largest_step_fraction": float(fraction),
        "is_step_like_target": int(is_step_like),
    }


def _best_trajectory_lag(
    start_s: float,
    end_s: float,
    current: ScalarStream,
    target: ScalarStream,
    config: AnalysisConfig,
) -> tuple[float, float]:
    """Find the target delay that best matches current position during a command."""

    mask = (current.time_s >= start_s) & (current.time_s <= end_s)
    query_t = current.time_s[mask]
    actual = current.value[mask]
    if len(query_t) < 10:
        return np.nan, np.nan

    if len(query_t) > config.lag_max_samples:
        selected = np.linspace(0, len(query_t) - 1, config.lag_max_samples).astype(np.int64)
        query_t = query_t[selected]
        actual = actual[selected]

    best_lag = np.nan
    best_rmse = np.inf
    lag_values = np.arange(0.0, config.lag_max_s + config.lag_step_s / 2.0, config.lag_step_s)

    for lag_s in lag_values:
        valid = query_t - lag_s >= target.time_s[0]
        if int(np.sum(valid)) < 10:
            continue
        delayed_target = zero_order_hold(target.time_s, target.value, query_t[valid] - lag_s)
        rmse = float(np.sqrt(np.mean((actual[valid] - delayed_target) ** 2)))
        if rmse < best_rmse:
            best_lag = float(lag_s)
            best_rmse = rmse

    return best_lag, best_rmse if np.isfinite(best_rmse) else np.nan


def _measure_shot_axis(
    axis: str,
    fire_time_s: float,
    streams: dict[str, ScalarStream],
    config: AnalysisConfig,
) -> dict[str, float | int]:
    current = streams[_motor_path(axis, "current")]
    target = streams[_motor_path(axis, "target")]
    mask = (current.time_s >= fire_time_s - config.shot_pre_s) & (
        current.time_s <= fire_time_s + config.shot_post_s
    )
    query_t = current.time_s[mask]
    actual = current.value[mask]

    prefix = f"{axis}_"
    if len(query_t) < 5:
        return {
            f"{prefix}peak_signed_deg": np.nan,
            f"{prefix}peak_abs_deg": np.nan,
            f"{prefix}peak_time_s": np.nan,
            f"{prefix}recovery_s": np.nan,
            f"{prefix}target_range_deg": np.nan,
            f"{prefix}target_stable": 0,
        }

    target_at_current = zero_order_hold(target.time_s, target.value, query_t)
    error = actual - target_at_current
    baseline_mask = (query_t >= fire_time_s - config.shot_pre_s) & (
        query_t < fire_time_s - config.shot_baseline_ignore_s
    )
    if np.any(baseline_mask):
        baseline_error = float(np.median(error[baseline_mask]))
    else:
        before_fire = query_t < fire_time_s
        baseline_error = float(np.median(error[before_fire])) if np.any(before_fire) else float(error[0])

    deviation = error - baseline_error
    post_mask = (query_t >= fire_time_s) & (query_t <= fire_time_s + config.shot_post_s)
    post_t = query_t[post_mask]
    post_deviation = deviation[post_mask]
    peak_local_idx = int(np.argmax(np.abs(post_deviation)))
    peak_signed = float(post_deviation[peak_local_idx])
    peak_abs = abs(peak_signed)
    peak_time_s = float(post_t[peak_local_idx] - fire_time_s)

    target_window_mask = (target.time_s >= fire_time_s - config.shot_pre_s) & (
        target.time_s <= fire_time_s + config.shot_post_s
    )
    endpoint_targets = zero_order_hold(
        target.time_s,
        target.value,
        np.array([fire_time_s - config.shot_pre_s, fire_time_s + config.shot_post_s]),
    )
    target_range = float(abs(endpoint_targets[1] - endpoint_targets[0]))
    if np.any(target_window_mask):
        target_range = max(target_range, float(np.ptp(target.value[target_window_mask])))

    peak_global_idx = np.flatnonzero(post_mask)[peak_local_idx]
    recovery_threshold = max(config.shot_recovery_floor_deg, config.shot_recovery_fraction_of_peak * peak_abs)
    recovery_s = _first_stable_time(
        query_t[peak_global_idx:],
        np.abs(deviation[peak_global_idx:]),
        recovery_threshold,
        config.settle_hold_s,
        fire_time_s,
    )

    return {
        f"{prefix}peak_signed_deg": peak_signed,
        f"{prefix}peak_abs_deg": peak_abs,
        f"{prefix}peak_time_s": peak_time_s,
        f"{prefix}recovery_s": recovery_s,
        f"{prefix}target_range_deg": target_range,
        f"{prefix}target_stable": int(target_range <= config.shot_stable_target_range_deg),
    }


def _first_stable_time(
    times_s: np.ndarray,
    abs_error: np.ndarray,
    tolerance: float,
    hold_s: float,
    origin_s: float,
) -> float:
    if len(times_s) == 0:
        return np.nan
    for idx in range(len(times_s)):
        end_idx = int(np.searchsorted(times_s, times_s[idx] + hold_s, side="left"))
        if end_idx >= len(times_s):
            return np.nan
        if np.all(abs_error[idx : end_idx + 1] <= tolerance):
            return float(times_s[end_idx] - origin_s)
    return np.nan


def _movement_summary_row(
    axis: str,
    magnitude_bin: str,
    rows: list[dict[str, float | int | str]],
) -> dict[str, float | int | str]:
    return {
        "axis": axis,
        "magnitude_bin": magnitude_bin,
        "episodes": len(rows),
        "arrival_n": int(np.isfinite(_array(rows, "arrival_latency_s")).sum()),
        "arrival_median_s": _safe_percentile(_finite_values(rows, "arrival_latency_s"), 50),
        "arrival_p90_s": _safe_percentile(_finite_values(rows, "arrival_latency_s"), 90),
        "settling_n": int(np.isfinite(_array(rows, "settling_time_s")).sum()),
        "settling_median_s": _safe_percentile(_finite_values(rows, "settling_time_s"), 50),
        "settling_p90_s": _safe_percentile(_finite_values(rows, "settling_time_s"), 90),
        "trajectory_lag_n": int(np.isfinite(_array(rows, "trajectory_lag_s")).sum()),
        "trajectory_lag_median_s": _safe_percentile(_finite_values(rows, "trajectory_lag_s"), 50),
        "trajectory_lag_p90_s": _safe_percentile(_finite_values(rows, "trajectory_lag_s"), 90),
        "overshoot_median_deg": _safe_percentile(_finite_values(rows, "overshoot_abs_deg"), 50),
        "overshoot_p90_deg": _safe_percentile(_finite_values(rows, "overshoot_abs_deg"), 90),
    }


def _finite_values(rows: Iterable[dict[str, float | int | str]], key: str) -> np.ndarray:
    values = _array(list(rows), key)
    return values[np.isfinite(values)]


def _array(rows: list[dict[str, float | int | str]], key: str) -> np.ndarray:
    return np.array([float(row.get(key, np.nan)) for row in rows], dtype=np.float64)


def _safe_percentile(values: np.ndarray, percentile: float) -> float:
    if len(values) == 0:
        return np.nan
    return float(np.percentile(values, percentile))


def _r2(y: np.ndarray, predicted: np.ndarray) -> float:
    total = float(np.sum((y - np.mean(y)) ** 2))
    if total == 0.0:
        return np.nan
    residual = float(np.sum((y - predicted) ** 2))
    return 1.0 - residual / total


def _next_delta_s(
    start_s: float,
    event_times_s: np.ndarray | None,
    config: AnalysisConfig,
) -> float:
    if event_times_s is None:
        return np.nan
    idx = int(np.searchsorted(event_times_s, start_s, side="left"))
    if idx >= len(event_times_s):
        return np.nan
    delta = float(event_times_s[idx] - start_s)
    return delta if 0.0 <= delta <= config.trigger_pair_max_s else np.nan


def _motor_path(axis: str, kind: str) -> str:
    return f"/motors/position/{axis}/{kind}"
