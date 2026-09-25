# -*- coding: utf-8 -*-
"""
سراب - اختبارات التحقق (شغّلها بعد أي تعديل قبل الدفع إلى GitHub)

يغطي:
  1) أن simulation.py ما زال يعطي نفس أرقام سرب المرجعية (0 مخالفات، 9.4%)
  2) أن نموذج التوقّع المصدَّر عبر OpenVINO يطابق نموذج sklearn نفسه (وليس فقط
     "يبدو منطقيًا") - هذا هو الفحص الذي كشف مشكلتين حقيقيتين أثناء البناء:
     ضغط FP16 الافتراضي عند الحفظ، ودقة bfloat16 الافتراضية لتشغيل CPU.

شغّله بـ: python3 test_pipeline.py
"""

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
sys.path.insert(0, str(REPO_ROOT / "ml"))  # so `from train_model import ...` below resolves

FAILURES = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print("[{}] {}{}".format(status, name, "  - " + detail if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


def test_simulation_numbers():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "simulation.py")],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    out = result.stdout
    check("simulation.py runs without error", result.returncode == 0)
    check("baseline energy is 1629.90 kWh", "1629.90" in out)
    check("sarab energy is 1476.30 kWh", "1476.30" in out)
    check("savings is 9.4%", "9.4%" in out)
    check("zero hard-constraint violations", "sarab   : 0" in out)
    check("CostAgent win count reflects the fix (144)", "CostAgent     : 144" in out)
    check("ComfortAgent win count reflects the fix (129)", "ComfortAgent  : 129" in out)


def test_predictor_matches_sklearn(tolerance=1e-4, n_samples=50):
    from train_model import train_and_evaluate, FEATURE_COLUMNS
    from predictor import OccupancyPredictor

    model, metrics = train_and_evaluate()
    check("model recall is not degenerately low (>0.4)", metrics["recall"] > 0.4,
          "recall={:.3f}".format(metrics["recall"]))

    predictor = OccupancyPredictor()
    df = pd.read_csv(DATA_DIR / "occupancy_training_data.csv")
    sample = df.sample(n_samples, random_state=1)

    max_diff = 0.0
    for _, row in sample.iterrows():
        x = row[FEATURE_COLUMNS].to_numpy(dtype=np.float32).reshape(1, -1)
        sklearn_p = model.predict_proba(x.astype(np.float64))[0, 1]
        hour = next(h for h in range(24) if row["hour_{}".format(h)] == 1)
        pattern = next(
            p for p in ["classroom", "corridor", "critical", "office"] if row["pattern_" + p] == 1
        )
        ov_p = predictor.predict_proba(hour, row["is_weekend"], pattern, row["prev_occupied"])
        max_diff = max(max_diff, abs(sklearn_p - ov_p))

    check(
        "OpenVINO predictions match sklearn within {} (n={})".format(tolerance, n_samples),
        max_diff < tolerance,
        "max_diff={:.6f}".format(max_diff),
    )


def test_predictor_input_validation():
    from predictor import OccupancyPredictor

    predictor = OccupancyPredictor()
    try:
        predictor.predict_proba(25, 0, "classroom", 0)
        check("rejects out-of-range hour", False)
    except ValueError:
        check("rejects out-of-range hour", True)

    try:
        predictor.predict_proba(9, 0, "gym", 0)
        check("rejects unknown zone pattern", False)
    except ValueError:
        check("rejects unknown zone pattern", True)


if __name__ == "__main__":
    print("=== 1. simulation.py regression ===")
    test_simulation_numbers()
    print("\n=== 2. Predictor vs. sklearn fidelity ===")
    test_predictor_matches_sklearn()
    print("\n=== 3. Predictor input validation ===")
    test_predictor_input_validation()

    print()
    if FAILURES:
        print("{} CHECK(S) FAILED: {}".format(len(FAILURES), FAILURES))
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED")
