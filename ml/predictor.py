# -*- coding: utf-8 -*-
"""
سراب - المرحلة الخامسة: غلاف التوقّع (Predictor Wrapper)

يحمّل نموذج OpenVINO IR الناتج من train_model.py مرة واحدة، ثم يوفّر دالة
predict() بسيطة تُستدعى من داخل حلقة المحاكاة (ولاحقًا من نظام حقيقي) لكل
منطقة/ساعة، فتُرجع: هل يُتوقع أن تكون المنطقة مشغولة في الساعة القادمة؟

مهم: ترتيب الميزات هنا يجب أن يطابق FEATURE_COLUMNS في train_model.py حرفيًا
(نفس الترتيب الذي دُرّب عليه النموذج)، وإلا فالتوقعات ستكون بلا معنى دون أي
خطأ ظاهر يُنبّهك.
"""

import numpy as np
import openvino as ov
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "models"

HOUR_COLUMNS = ["hour_{}".format(h) for h in range(24)]
FEATURE_ORDER = (
    ["is_weekend", "prev_occupied"]
    + HOUR_COLUMNS
    + ["pattern_classroom", "pattern_corridor", "pattern_critical", "pattern_office"]
)
KNOWN_PATTERNS = ["classroom", "corridor", "critical", "office"]
DECISION_THRESHOLD = 0.5


class OccupancyPredictor:
    def __init__(self, ir_path=None, device="CPU"):
        if ir_path is None:
            ir_path = MODELS_DIR / "occupancy_model.xml"
        core = ov.Core()
        model = core.read_model(ir_path)
        # The CPU plugin can silently default to bfloat16 internal execution
        # for speed (confirmed on this machine: core.get_property('CPU',
        # ov.properties.hint.inference_precision) returned bfloat16), even
        # though the IR itself is FP32. bf16 has ~3 decimal digits of
        # precision, which was producing ~1e-3 drift from the trained
        # sklearn model's actual probabilities. Forcing FP32 here trades a
        # small amount of speed (irrelevant for a model this size) for being
        # bit-faithful to what was actually trained and evaluated.
        config = {ov.properties.hint.inference_precision: ov.Type.f32}
        self._compiled = core.compile_model(model, device, config)
        self._output = self._compiled.output(0)

    def predict_proba(self, hour, is_weekend, pattern, prev_occupied):
        """يرجع احتمال الإشغال في الساعة القادمة (0.0 - 1.0)."""
        if pattern not in KNOWN_PATTERNS:
            raise ValueError(
                "نمط غير معروف: {!r} - يجب أن يكون أحد {}".format(pattern, KNOWN_PATTERNS)
            )

        if not (0 <= hour <= 23):
            raise ValueError("hour يجب أن يكون بين 0 و23، وردت: {}".format(hour))

        row = {name: 0.0 for name in FEATURE_ORDER}
        row["is_weekend"] = float(is_weekend)
        row["prev_occupied"] = float(prev_occupied)
        row["hour_{}".format(hour)] = 1.0
        row["pattern_{}".format(pattern)] = 1.0

        x = np.array([[row[name] for name in FEATURE_ORDER]], dtype=np.float32)
        result = self._compiled([x])[self._output]
        return float(result[0, 0])

    def predict(self, hour, is_weekend, pattern, prev_occupied):
        """يرجع True/False: هل يُتوقع الإشغال في الساعة القادمة."""
        proba = self.predict_proba(hour, is_weekend, pattern, prev_occupied)
        return proba >= DECISION_THRESHOLD


if __name__ == "__main__":
    # فحص سريع: يجب أن يعطي نتائج منطقية (مثلاً فصل دراسي صباح يوم عمل بعد
    # ساعة مشغولة => احتمال إشغال عالٍ)
    predictor = OccupancyPredictor()
    cases = [
        (8, 0, "classroom", 1, "فصل، ٨ص، يوم عمل، كانت مشغولة"),
        (3, 0, "classroom", 0, "فصل، ٣ص، يوم عمل، لم تكن مشغولة"),
        (10, 1, "office", 0, "مكتب، ١٠ص، عطلة أسبوعية"),
    ]
    for hour, is_weekend, pattern, prev_occ, label in cases:
        p = predictor.predict_proba(hour, is_weekend, pattern, prev_occ)
        print("{:<45s} -> P(occupied_next_hour) = {:.3f}".format(label, p))
