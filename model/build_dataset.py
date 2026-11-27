"""Build the training table for the vehicle-availability model.

One row per (grid cell, stored 10-minute snapshot) with targets, features and
baseline columns. Johannes trains on this in model/train.py from Tuesday on.

The two targets are "available" (at least one rentable vehicle in the cell
during this snapshot) and "available_nearby" (same, but any of the 3x3
cells around it, including itself). Features are split into two groups:
  A: only needs cell, time, the data history and Moritz' hourly weather
     (model/weather.py). The app can compute Group A offline, because
     tomorrow's weather forecast is known the evening before.
  B: needs the live fleet, so the app has to call the sharedmobility.ch API
     when it renders the prediction page.

Data-leakage rule: every feature is as of the forecast moment, which is the
evening before the predicted day at 22:00 local time. The docstring of each
feature says why it is not a leak.

Usage:
    python3 model/build_dataset.py [--vehicle scooter|bike] [--threshold 0.10]

AI citation: this file was generated with Claude Code (model Claude Opus 4.7,
Anthropic) on 2026-11-27 and reviewed by the project team.
"""

import argparse
import sys
import time as time_module
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

MODEL_DIR = Path(__file__).resolve().parent
PROJECT_DIR = MODEL_DIR.parent
DATASET_DIR = MODEL_DIR / "dataset"
ARTIFACTS_DIR = MODEL_DIR / "artifacts"
WEATHER_CACHE = ARTIFACTS_DIR / "weather_history.csv"

sys.path.insert(0, str(MODEL_DIR))
sys.path.insert(0, str(PROJECT_DIR / "analysis"))
sys.path.insert(0, str(PROJECT_DIR / "collector"))

from load_data import iter_snapshots  # noqa: E402
from collect import cell_center  # noqa: E402
from build_baseline import classify_vehicle  # noqa: E402
import weather as weather_module  # noqa: E402

CITY = "st_gallen"
DEFAULT_THRESHOLD = 0.10
LECTURE_FREE_START = date(2026, 11, 2)
LECTURE_FREE_END = date(2026, 11, 8)

# One stable place for the train/test split: all rows before SPLIT_DATE go
# into train, from SPLIT_DATE onward into test. A day-wise split is used
# because all cells of one day share the same fleet size, weather and
# nightly Dott redistribution. A random row split would let the model learn
# the day and give overly optimistic test scores.
SPLIT_DATE = date(2026, 11, 21)

FEATURES_A = [
    "hour",
    "minute_of_day",
    "weekday",
    "is_weekend",
    "lecture_period",
    "lat",
    "lon",
    "rate_cell",
    "rate_nearby",
    "recent_cell",
    "recent_nearby",
    "history_days",
    "temperature_c",
    "precipitation_mm",
]
FEATURES_B = [
    "evening_count_cell",
    "evening_count_nearby",
    "evening_fleet",
]
TARGETS = ["available", "available_nearby"]
BASELINES = ["baseline_week", "baseline_week_nearby", "baseline_evening"]

OUTPUT_COLUMNS = (
    ["time", "cell_id", "vehicle"] + TARGETS + FEATURES_A + FEATURES_B + BASELINES
)

NEIGHBOUR_OFFSETS = [(dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1)]


def read_raw(city, vehicle, data_dir=None):
    """Read all snapshots and return (df_raw, slot_times, outage_skipped).

    df_raw has one row per (snapshot time, cell) that held at least one
    vehicle of the given type, with the summed count across providers.
    slot_times is the sorted list of every stored snapshot time, including
    those in which no vehicle of the given type was present.

    Reading goes through analysis.load_data.iter_snapshots, which already
    converts timestamps to Europe/Zurich and drops outages listed in
    analysis/outages.csv, so the training data matches the analyses.
    """
    kwargs = {"data_dir": data_dir} if data_dir is not None else {}
    raw_rows = []
    slot_times = set()
    for row in iter_snapshots(city, **kwargs):
        slot_times.add(row["time"])
        if classify_vehicle(row["vehicle_type_id"]) != vehicle:
            continue
        raw_rows.append((row["time"], row["cell_id"], row["count"]))

    if not raw_rows:
        raise RuntimeError(
            f"no rows for vehicle={vehicle!r} in city={city!r}, nothing to build"
        )

    df_raw = (
        pd.DataFrame(raw_rows, columns=["time", "cell_id", "count"])
        .groupby(["time", "cell_id"], as_index=False)["count"].sum()
    )
    return df_raw, sorted(slot_times)


def pick_cells(df_raw, slot_times, threshold):
    """Return the sorted list of cells that cleared the availability threshold.

    A cell is included if it had at least one vehicle in at least
    threshold * len(slot_times) distinct snapshots. Neighbouring cells below
    the threshold still contribute to available_nearby and evening_count_nearby.
    """
    cells_per_slot_count = df_raw.groupby("cell_id")["time"].nunique()
    minimum = threshold * len(slot_times)
    kept = cells_per_slot_count[cells_per_slot_count >= minimum].index
    return sorted(kept)


def _add_cell_coords(cell_series):
    """Return (lat, lon) arrays for a Series of cell_ids, using cell_center()."""
    unique = cell_series.unique()
    centers = {c: cell_center(c) for c in unique}
    lats = cell_series.map(lambda c: centers[c][0])
    lons = cell_series.map(lambda c: centers[c][1])
    return lats.to_numpy(), lons.to_numpy()


def _neighbours(cell_id):
    """Return the 8 neighbour cell_ids around a cell (not the cell itself)."""
    row, col = (int(part) for part in cell_id.split("_"))
    return [
        f"{row + dr}_{col + dc}"
        for dr, dc in NEIGHBOUR_OFFSETS
        if (dr, dc) != (0, 0)
    ]


def _expand_to_neighbours(df_cells_times, keep_counts):
    """Explode a (time, cell_id[, count]) frame to all cells in the 3x3 area.

    For each input row, 9 rows come out, one per (dr, dc) offset. The result
    is used both for the OR-based available_nearby target (keep_counts=False,
    then drop duplicates) and for the sum-based evening_count_nearby feature
    (keep_counts=True, then groupby-sum).
    """
    columns = ["time", "row", "col"] + (["count"] if keep_counts else [])
    frames = []
    for dr, dc in NEIGHBOUR_OFFSETS:
        frame = df_cells_times[columns].copy()
        frame["row"] = frame["row"] + dr
        frame["col"] = frame["col"] + dc
        frames.append(frame)
    expanded = pd.concat(frames, ignore_index=True)
    expanded["cell_id"] = expanded["row"].astype(str) + "_" + expanded["col"].astype(str)
    out_cols = ["time", "cell_id"] + (["count"] if keep_counts else [])
    return expanded[out_cols]


def build_targets(base, df_raw):
    """Add 0/1 columns `available` and `available_nearby` to base.

    `available` is 1 when the (time, cell) pair appears in df_raw. A cell
    missing from a stored snapshot means zero vehicles, so the left merge
    with fillna(0) is exactly the rule in the CLAUDE.md.

    `available_nearby` is 1 when the cell or any of its 8 neighbours held a
    vehicle at this snapshot. Neighbours below the kept-cell threshold still
    count, because the raw data knows about them.
    """
    df_present = df_raw[["time", "cell_id"]].copy()
    df_present["available"] = 1
    base = base.merge(df_present, on=["time", "cell_id"], how="left")
    base["available"] = base["available"].fillna(0).astype("int8")

    df_raw_rc = df_raw[["time", "cell_id"]].copy()
    df_raw_rc[["row", "col"]] = df_raw_rc["cell_id"].str.split("_", expand=True).astype(int)
    nearby = _expand_to_neighbours(df_raw_rc, keep_counts=False).drop_duplicates()
    nearby["available_nearby"] = 1
    base = base.merge(nearby, on=["time", "cell_id"], how="left")
    base["available_nearby"] = base["available_nearby"].fillna(0).astype("int8")
    return base


def add_time_features(base):
    """Add hour, minute_of_day, weekday, is_weekend, lecture_period.

    None of these need other rows, so there is no leak: they are derived
    from the slot's own time only. lecture_period is 0 for the HSG autumn
    break (2026-11-02 to 2026-11-08) and 1 otherwise.
    """
    base["hour"] = base["time"].dt.hour.astype("int16")
    base["minute_of_day"] = (base["time"].dt.hour * 60 + base["time"].dt.minute).astype("int16")
    base["weekday"] = base["time"].dt.weekday.astype("int8")
    base["is_weekend"] = (base["weekday"] >= 5).astype("int8")
    local_dates = base["time"].dt.date
    in_break = (local_dates >= LECTURE_FREE_START) & (local_dates <= LECTURE_FREE_END)
    base["lecture_period"] = (~in_break).astype("int8")
    return base


def add_coordinates(base):
    """Add lat and lon of the cell center. Pure function of cell_id, no leak."""
    lat, lon = _add_cell_coords(base["cell_id"])
    base["lat"] = lat
    base["lon"] = lon
    return base


def add_rate_features(base):
    """Add rate_cell, rate_nearby, recent_cell, recent_nearby, history_days.

    Growing-window rule (no leak): per (cell, hour, is_weekend) sort days in
    time order. For day D, rate_cell(D) is the mean of the daily-availability
    rates from all earlier days of the same weekday type. The daily rate is
    the share of this day's stored slots in that hour in which the cell was
    available, so the aggregated rate matches the per-slot target.

    expanding().mean().shift(1) excludes day D itself from its own rate.
    recent uses rolling(3, min_periods=1).mean().shift(1), so it already
    returns a value when only one or two prior days exist. history_days
    counts those prior days and tells train.py how trustworthy the rates
    are; it is NaN before the first prior day, because 0 would imply "zero
    history days" which is not the same meaning as "no prior data at all".
    """
    base["date"] = base["time"].dt.normalize()
    daily = (
        base.groupby(["cell_id", "date", "hour"], as_index=False, sort=False)
        .agg(
            avail_cell_day=("available", "mean"),
            avail_nearby_day=("available_nearby", "mean"),
        )
    )
    daily["is_weekend"] = (daily["date"].dt.weekday >= 5).astype("int8")
    daily = daily.sort_values(["cell_id", "hour", "is_weekend", "date"]).reset_index(drop=True)
    grp = daily.groupby(["cell_id", "hour", "is_weekend"], sort=False)

    daily["rate_cell"] = grp["avail_cell_day"].transform(
        lambda s: s.shift(1).expanding().mean()
    )
    daily["recent_cell"] = grp["avail_cell_day"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).mean()
    )
    daily["rate_nearby"] = grp["avail_nearby_day"].transform(
        lambda s: s.shift(1).expanding().mean()
    )
    daily["recent_nearby"] = grp["avail_nearby_day"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).mean()
    )
    daily["history_days"] = grp["avail_cell_day"].transform(
        lambda s: s.shift(1).expanding().count()
    )
    # count() returns 0 for the first row; translate that to NaN per the docstring.
    daily.loc[daily["history_days"] == 0, "history_days"] = np.nan

    merged = base.merge(
        daily[["cell_id", "date", "hour", "rate_cell", "recent_cell", "rate_nearby",
               "recent_nearby", "history_days"]],
        on=["cell_id", "date", "hour"],
        how="left",
    )
    return merged


def add_evening_features(base, df_raw, slot_times):
    """Add evening_count_cell, evening_count_nearby, evening_fleet.

    These three come from the latest stored snapshot of the previous day
    between 18:00 and 22:00 local time (22:00 included, 22:10 and later not).
    If no such slot exists for that previous day, all three are NaN.

    This is the only Features B block: the app needs the live fleet from the
    sharedmobility.ch API to compute these at run time. No leak, because
    "last evening slot <= 22:00" is strictly before the 22:00 forecast
    moment of the following day.
    """
    slot_series = pd.Series(slot_times)
    slot_df = pd.DataFrame({"time": slot_series})
    slot_df["date"] = slot_df["time"].dt.normalize()
    slot_df["hour"] = slot_df["time"].dt.hour
    slot_df["minute"] = slot_df["time"].dt.minute

    in_evening = (
        ((slot_df["hour"] >= 18) & (slot_df["hour"] < 22))
        | ((slot_df["hour"] == 22) & (slot_df["minute"] == 0))
    )
    evening_slots = slot_df[in_evening].copy()
    latest_per_day = (
        evening_slots.sort_values("time")
        .drop_duplicates("date", keep="last")[["date", "time"]]
        .rename(columns={"date": "prev_date", "time": "evening_slot"})
    )

    # Fleet total per snapshot (across all cells of the chosen vehicle).
    fleet_per_slot = df_raw.groupby("time")["count"].sum().rename("evening_fleet")

    # Nearby count sum per (snapshot, cell): expand each raw row to 9
    # neighbours, keep the count, sum by (time, neighbour_cell).
    df_raw_rc = df_raw.copy()
    df_raw_rc[["row", "col"]] = df_raw_rc["cell_id"].str.split("_", expand=True).astype(int)
    nearby_expanded = _expand_to_neighbours(df_raw_rc, keep_counts=True)
    nearby_count_per_slot_cell = (
        nearby_expanded.groupby(["time", "cell_id"])["count"].sum()
        .rename("evening_count_nearby")
    )

    count_per_slot_cell = df_raw.set_index(["time", "cell_id"])["count"].rename(
        "evening_count_cell"
    )

    base["prev_date"] = base["date"] - pd.Timedelta(days=1)
    base = base.merge(latest_per_day, on="prev_date", how="left")

    # Look up the three evening values. The slot may exist but the cell may
    # be empty in it (then count=0, not NaN). Only a missing evening_slot
    # altogether yields NaN.
    for col, series in (
        ("evening_count_cell", count_per_slot_cell),
        ("evening_count_nearby", nearby_count_per_slot_cell),
    ):
        index = pd.MultiIndex.from_arrays([base["evening_slot"], base["cell_id"]])
        values = series.reindex(index).to_numpy()
        base[col] = np.where(base["evening_slot"].notna(), np.nan_to_num(values, nan=0.0), np.nan)

    base["evening_fleet"] = base["evening_slot"].map(fleet_per_slot)

    return base.drop(columns=["prev_date", "evening_slot"])


def calibrate_evening_baseline(df, split_date=None):
    """Fill the baseline_evening column using probabilities from training rows.

    For each is_weekend segment two numbers are learnt from rows before
    split_date:
      P(available=1 | evening_count_cell > 0) and
      P(available=1 | evening_count_cell == 0)
    Every row of df then receives the probability that matches its own
    (is_weekend, evening_count_cell > 0) cell. Rows where
    evening_count_cell is NaN (no stored evening slot) stay NaN, so the
    baseline is undefined when the evening fleet is unknown. Separating
    workday and weekend keeps this honest, because the commuter pattern
    differs strongly.
    """
    if split_date is None:
        split_date = SPLIT_DATE
    out = df.copy()
    out["baseline_evening"] = np.nan
    train_mask = out["time"].dt.date < split_date
    for ws in (0, 1):
        seg_train = out[train_mask & (out["is_weekend"] == ws)]
        valid = seg_train.dropna(subset=["evening_count_cell", "available"])
        has_ev = valid.loc[valid["evening_count_cell"] > 0, "available"]
        no_ev = valid.loc[valid["evening_count_cell"] == 0, "available"]
        p_with = float(has_ev.mean()) if len(has_ev) else float("nan")
        p_without = float(no_ev.mean()) if len(no_ev) else float("nan")

        seg_all = out["is_weekend"] == ws
        out.loc[seg_all & (out["evening_count_cell"] > 0), "baseline_evening"] = p_with
        out.loc[seg_all & (out["evening_count_cell"] == 0), "baseline_evening"] = p_without
    return out


def load_weather(cache_path=WEATHER_CACHE):
    """Return hourly weather history, from the live API with a CSV fallback.

    The build calls get_history() once and writes the result to
    model/artifacts/weather_history.csv, so the next build (and the handed-in
    archive without internet) can still run. If the live call fails and the
    cache is present, the cache is loaded and a note is printed. If neither
    works, RuntimeError is raised: the build cannot continue without weather.
    """
    try:
        weather_df = weather_module.get_history()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        to_save = weather_df.copy()
        to_save["time"] = to_save["time"].dt.strftime("%Y-%m-%dT%H:%M:%S%z")
        to_save.to_csv(cache_path, index=False)
        print(f"weather: fetched from Open-Meteo, cached to {cache_path.name}")
        return weather_df
    except Exception as error:  # pragma: no cover
        if not cache_path.exists():
            raise RuntimeError(
                f"no weather from Open-Meteo and no cached {cache_path.name}: {error}"
            ) from error
        print(f"weather: Open-Meteo unreachable ({error}); using cached {cache_path.name}")
        cached = pd.read_csv(cache_path)
        cached["time"] = pd.to_datetime(cached["time"], utc=True).dt.tz_convert(
            "Europe/Zurich"
        )
        return cached


def add_weather_features(base, weather_df):
    """Add temperature_c and precipitation_mm to base by hourly ceil join.

    Open-Meteo's precipitation for 08:00 is the rain that fell between 07:00
    and 08:00, so a slot at 07:10 belongs to the 08:00 weather row. A slot
    at exactly 08:00 also keeps the 08:00 row (ceil of 08:00 is 08:00).
    No leak: tomorrow's hourly forecast is known the evening before.
    Missing hours stay NaN so train.py can decide how to handle them.
    """
    ceiled = base["time"].dt.ceil("h")
    base = base.copy()
    base["_weather_hour"] = ceiled
    wx = weather_df[["time", "temperature_c", "precipitation_mm"]].rename(
        columns={"time": "_weather_hour"}
    )
    base = base.merge(wx, on="_weather_hour", how="left")
    return base.drop(columns=["_weather_hour"])


def add_baseline_features(base):
    """Add baseline_week and baseline_week_nearby.

    These are the naive "same cell, exactly 7 days earlier" references.
    Looked up by (time - 7 days, cell_id). If the earlier snapshot was not
    stored (outage or gap), the baseline is NaN. The strong baseline is
    rate_cell itself, not these columns.
    """
    lookup_cell = base.set_index(["time", "cell_id"])["available"]
    lookup_nearby = base.set_index(["time", "cell_id"])["available_nearby"]

    shifted_times = base["time"] - pd.Timedelta(days=7)
    index = pd.MultiIndex.from_arrays([shifted_times, base["cell_id"]])
    base["baseline_week"] = lookup_cell.reindex(index).to_numpy()
    base["baseline_week_nearby"] = lookup_nearby.reindex(index).to_numpy()
    return base


def build(vehicle, threshold, data_dir=None, weather_df=None):
    """Return the full training table as a pandas DataFrame.

    Pure function: reads via analysis.load_data.iter_snapshots, computes
    targets, features and baselines, and returns the combined frame. Used
    both from the CLI (main writes it to disk) and from the tests. The
    weather_df argument lets tests inject a tiny DataFrame instead of
    calling Open-Meteo; the CLI leaves it None and load_weather() handles
    fetch and cache.
    """
    df_raw, slot_times = read_raw(CITY, vehicle, data_dir=data_dir)
    cells = pick_cells(df_raw, slot_times, threshold)
    if not cells:
        raise RuntimeError(
            f"no cells cleared threshold={threshold!r} for vehicle={vehicle!r}"
        )

    base = pd.MultiIndex.from_product(
        [cells, slot_times], names=["cell_id", "time"]
    ).to_frame(index=False)
    base["vehicle"] = vehicle

    base = build_targets(base, df_raw)
    base = add_time_features(base)
    base = add_coordinates(base)
    base = add_rate_features(base)
    base = add_evening_features(base, df_raw, slot_times)
    base = add_baseline_features(base)

    if weather_df is None:
        weather_df = load_weather()
    base = add_weather_features(base, weather_df)

    base = calibrate_evening_baseline(base)

    return base[OUTPUT_COLUMNS].sort_values(["time", "cell_id"]).reset_index(drop=True)


def save(df, vehicle, dataset_dir=DATASET_DIR):
    """Write df to dataset_dir/training_<vehicle>.csv.gz with ISO time strings."""
    dataset_dir.mkdir(parents=True, exist_ok=True)
    path = dataset_dir / f"training_{vehicle}.csv.gz"
    out = df.copy()
    out["time"] = out["time"].dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    out.to_csv(path, index=False, compression="gzip")
    return path


def load_training_table(vehicle, dataset_dir=DATASET_DIR):
    """Read back a saved training table with tz-aware Europe/Zurich time."""
    path = dataset_dir / f"training_{vehicle}.csv.gz"
    df = pd.read_csv(path, compression="gzip")
    df["time"] = pd.to_datetime(df["time"], utc=True).dt.tz_convert("Europe/Zurich")
    return df


def split_by_day(df):
    """Return (train, test) split at SPLIT_DATE. See the SPLIT_DATE comment."""
    dates = df["time"].dt.date
    train = df[dates < SPLIT_DATE].copy().reset_index(drop=True)
    test = df[dates >= SPLIT_DATE].copy().reset_index(drop=True)
    return train, test


def _brier(y, p):
    """Mean squared error of a probability prediction. Lower is better."""
    return float(((p - y) ** 2).mean())


def _false_alarm_rate(y, p, threshold=0.7):
    """Share of rows where the forecast is >= threshold but the target is 0."""
    mask = p >= threshold
    if not mask.any():
        return 0.0
    return float(((mask) & (y == 0)).mean())


def _evaluate_block(test_block, train_df):
    """Print Brier, BSS vs. constant and false-alarm rate for both targets.

    Uses the same rows for all baselines of a target (dropna on everything
    at once), so the Brier scores are directly comparable. baseline_evening
    is only defined for `available`; it is dropped from the prediction list
    for `available_nearby`. The constant is the training mean of the target
    per is_weekend; it is both printed as its own Brier and used as the
    reference for every baseline's Brier Skill Score. The false-alarm rate
    is the share of rows where the baseline predicts >= 0.7 but the target
    is 0, that is, the "we promised a vehicle and none was there" case.
    """
    groups = [
        ("available", ["baseline_week", "rate_cell", "baseline_evening"]),
        ("available_nearby", ["baseline_week_nearby", "rate_nearby"]),
    ]
    for target, preds in groups:
        print(f"  {target}")
        for is_weekend, wlabel in ((0, "workday"), (1, "weekend")):
            train_seg = train_df[train_df["is_weekend"] == is_weekend]
            constant = float(train_seg[target].mean())
            seg = test_block[test_block["is_weekend"] == is_weekend]
            common = seg.dropna(subset=preds + [target])
            if common.empty:
                print(f"    {wlabel:7} no rows with all baselines present")
                continue
            y = common[target].to_numpy()
            p_const = np.full(len(y), constant)
            brier_const = _brier(y, p_const)
            fa_const = _false_alarm_rate(y, p_const)
            print(
                f"    {wlabel:7} n={len(common):>7_}  "
                f"constant Brier={brier_const:.4f} FA={fa_const:.3f} c={constant:.3f}  "
                f"actual mean={y.mean():.3f}"
            )
            for p in preds:
                brier_p = _brier(y, common[p])
                fa_p = _false_alarm_rate(y, common[p])
                bss = 1.0 - brier_p / brier_const if brier_const > 0 else float("nan")
                mean_pred = float(common[p].mean())
                print(
                    f"      {p:22} Brier={brier_p:.4f}  BSS={bss:+.3f}  "
                    f"FA={fa_p:.3f}  mean={mean_pred:.3f}"
                )


def _per_day_table(test_df, train_df):
    """Print one row per test day: date, weekday, n, mean fleet, Brier and actual.

    Replaces the earlier two-block split around 2026-11-23, which would have
    compared workdays against a weekend-only block (the test weekend 21./22.11.
    falls before the fleet drop and nothing else does). The per-day view makes
    the fleet shrink visible day by day via the mean evening_fleet column.
    """
    print(
        f"  {'date':10} {'wd':3} {'n':>7} {'mean_fleet':>10} {'actual':>7}"
        f" {'Brier rate':>10} {'Brier evening':>13} {'Brier const':>11}"
    )
    train_by_ws = {
        ws: float(train_df[train_df["is_weekend"] == ws]["available"].mean())
        for ws in (0, 1)
    }
    test_df = test_df.copy()
    test_df["_date"] = test_df["time"].dt.date
    for day in sorted(test_df["_date"].unique()):
        day_rows = test_df[test_df["_date"] == day]
        common = day_rows.dropna(
            subset=["baseline_week", "rate_cell", "baseline_evening", "available"]
        )
        if common.empty:
            print(f"  {day!s:10} (no rows with all baselines present)")
            continue
        is_weekend = int(common["is_weekend"].iloc[0])
        wd = day.strftime("%a")
        y = common["available"].to_numpy()
        mean_fleet = float(common["evening_fleet"].mean())
        constant = train_by_ws[is_weekend]
        print(
            f"  {day!s:10} {wd:3} {len(common):>7_} {mean_fleet:>10.1f} "
            f"{y.mean():>7.3f} {_brier(y, common['rate_cell']):>10.4f} "
            f"{_brier(y, common['baseline_evening']):>13.4f} "
            f"{_brier(y, np.full(len(y), constant)):>11.4f}"
        )


def evaluate(test_df, train_df):
    """Print Brier scores and Brier Skill Score for several test slices.

    Two aggregated blocks plus one per-day table are printed on the same
    test data:
      full test:    everything from SPLIT_DATE on
      workday 7-8h: hour 7:00 to 8:59, the commuter morning window
      per day:      one row per test date with the mean evening_fleet, so
                    the shrinking-fleet effect is visible day by day
    Each aggregated block runs _evaluate_block(). Three model-free
    baselines plus the constant are compared on rows where all of them
    are present:
      baseline_week:     naive "same slot seven days ago"
      rate_cell:         expanding-window per-cell/hour/is_weekend frequency
      baseline_evening:  calibrated P(available | evening_count_cell) from
                         the training rows, per is_weekend. This is the
                         strongest model-free reference and the real bar
                         the ML model has to beat.
      constant:          mean of the target in the training block
    """
    workday_morning = (test_df["is_weekend"] == 0) & test_df["hour"].between(7, 8)
    blocks = [
        ("full test block", test_df),
        ("workday 7-8h", test_df[workday_morning]),
    ]
    for label, block in blocks:
        print(f"\n=== {label}  (n={len(block):_}) ===")
        if block.empty:
            continue
        _evaluate_block(block, train_df)

    print("\n=== per-day summary ===")
    _per_day_table(test_df, train_df)


def main():
    """CLI entry point: build, save, evaluate and print build-time stats."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vehicle", choices=("scooter", "bike"), default="scooter")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    args = parser.parse_args()

    start = time_module.perf_counter()
    df = build(args.vehicle, args.threshold)
    path = save(df, args.vehicle)
    elapsed = time_module.perf_counter() - start

    n_rows = len(df)
    n_cells = df["cell_id"].nunique()
    share_cell = df["available"].mean()
    share_nearby = df["available_nearby"].mean()

    print(f"vehicle:              {args.vehicle}")
    print(f"threshold:            {args.threshold}")
    print(f"rows:                 {n_rows:_}")
    print(f"cells:                {n_cells}")
    print(f"share available=1:    {share_cell:.3f}")
    print(f"share avail_nearby=1: {share_nearby:.3f}")

    train_df, test_df = split_by_day(df)
    print(f"train rows (< {SPLIT_DATE}): {len(train_df):_}")
    print(f"test rows  (>= {SPLIT_DATE}): {len(test_df):_}")
    evaluate(test_df, train_df)

    print(f"\nbuild time:    {elapsed:.1f} s")
    print(f"file size:     {path.stat().st_size / 1_000_000:.2f} MB")
    print(f"written to:    {path}")


if __name__ == "__main__":
    main()
