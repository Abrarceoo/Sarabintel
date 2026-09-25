# -*- coding: utf-8 -*-
"""
سراب - المرحلة الثالثة: تحضير بيانات التدريب لنموذج توقّع الإشغال

يقرأ simulation_log.csv (الناتج من simulation.py) ويبني جدول تدريب لنموذج
يتوقع: هل ستكون المنطقة مشغولة في الساعة القادمة؟

الميزات (features):
    hour              - ساعة اليوم (0-23)
    is_weekend        - هل هو يوم عطلة (الجمعة/السبت وفق weekend في المحاكاة)
    pattern_*          - ترميز واحد ساخن (one-hot) لنمط المنطقة
                        (classroom / office / corridor / critical)
    prev_occupied     - هل كانت المنطقة مشغولة في الساعة السابقة (0/1)

الهدف (label):
    next_occupied     - هل ستكون المنطقة مشغولة في الساعة القادمة (0/1)

ملاحظة مهمة: نأخذ سيناريو baseline فقط من السجل لتفادي التكرار (الإشغال
نفسه في baseline و sarab، لأن كليهما يستخدمان نفس بيئة generate_environment
ونفس البذرة العشوائية). أول ساعة لكل منطقة ليس لها "ساعة سابقة" حقيقية،
فنفترض prev_occupied = 0 لها (افتراض صريح، وليس بيانات فعلية).
"""

import pandas as pd
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

# نفس تعريف الأنماط الموجود في ZONES داخل simulation.py
ZONE_PATTERN = {
    "classroom_1": "classroom",
    "classroom_2": "classroom",
    "office_1": "office",
    "corridor_1": "corridor",
    "or_1": "critical",
}

WEEKEND_DAYS = {5, 6}  # نفس WEEKEND_DAYS في simulation.py


def build_training_table(log_path=None):
    if log_path is None:
        log_path = DATA_DIR / "simulation_log.csv"
    df = pd.read_csv(log_path)
    df = df[df["scenario"] == "baseline"].copy()

    df["pattern"] = df["zone_id"].map(ZONE_PATTERN)
    if df["pattern"].isna().any():
        missing = df.loc[df["pattern"].isna(), "zone_id"].unique()
        raise ValueError(
            "zone_id غير معروف في ZONE_PATTERN: {} - حدّث القاموس أعلاه إن تغيّرت "
            "مناطق simulation.py".format(list(missing))
        )

    df["is_weekend"] = df["day"].isin(WEEKEND_DAYS).astype(int)

    df = df.sort_values(["zone_id", "day", "hour"]).reset_index(drop=True)

    # prev_occupied: إزاحة إلى الأمام ضمن كل منطقة على حدة
    df["prev_occupied"] = df.groupby("zone_id")["occupancy"].shift(1)
    df["prev_occupied"] = df["prev_occupied"].fillna(0).astype(int)

    # next_occupied (الهدف): إزاحة إلى الخلف ضمن كل منطقة على حدة
    df["next_occupied"] = df.groupby("zone_id")["occupancy"].shift(-1)
    # آخر ساعة لكل منطقة ليس لها "ساعة قادمة" ضمن السجل - نحذفها
    df = df.dropna(subset=["next_occupied"]).copy()
    df["next_occupied"] = df["next_occupied"].astype(int)

    pattern_dummies = pd.get_dummies(df["pattern"], prefix="pattern").astype(int)
    # hour is one-hot, not linear/ordinal: occupancy vs hour is hump-shaped
    # (low at night, rises through morning, peaks midday, drops in evening),
    # so a single linear coefficient for "hour" can't represent it - same
    # reasoning as why pattern is one-hot rather than an arbitrary number.
    hour_dummies = pd.get_dummies(df["hour"], prefix="hour").astype(int)

    feature_cols = ["is_weekend", "prev_occupied"]
    out = pd.concat(
        [df[["zone_id", "day"] + feature_cols], hour_dummies, pattern_dummies, df["next_occupied"]],
        axis=1,
    )
    return out


if __name__ == "__main__":
    table = build_training_table()
    DATA_DIR.mkdir(exist_ok=True)
    out_path = DATA_DIR / "occupancy_training_data.csv"
    table.to_csv(out_path, index=False)
    print("Saved ->", out_path)
    print("Rows:", len(table))
    print("Columns:", list(table.columns))
    print()
    print("Class balance (next_occupied):")
    print(table["next_occupied"].value_counts(normalize=True))
    print()
    print(table.head(8).to_string(index=False))
