# -*- coding: utf-8 -*-
"""
سراب - المرحلة السادسة: ضغط النموذج (NNCF) وقياس زمن الاستدلال

يأخذ نموذج OpenVINO IR الناتج من train_model.py (FP32)، يضغطه إلى INT8 عبر
NNCF (Post-Training Quantization)، ثم يقيس زمن الاستدلال الفعلي قبل وبعد -
وكذلك دقة النموذج قبل وبعد، لأن الضغط قد يكلّف بعض الدقة ولا يجوز إخفاء ذلك.

هذا هو الدليل المقاس (وليس المصمَّم فقط) على تشغيل Sarab عبر Intel edge AI.
"""

import time
from pathlib import Path

import numpy as np
import openvino as ov

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
MODELS_DIR = REPO_ROOT / "models"

N_WARMUP = 50
N_TIMED = 2000


def load_calibration_data(n=200):
    """يحمّل عينة من صفوف التدريب الفعلية لاستخدامها في معايرة الضغط."""
    import pandas as pd
    from train_model import FEATURE_COLUMNS

    df = pd.read_csv(DATA_DIR / "occupancy_training_data.csv")
    sample = df.sample(min(n, len(df)), random_state=7)
    X = sample[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    return X


def quantize(fp32_ir_path, int8_ir_path):
    import nncf

    core = ov.Core()
    fp32_model = core.read_model(fp32_ir_path)

    calibration_X = load_calibration_data()

    def transform_fn(row):
        return row.reshape(1, -1)

    calibration_dataset = nncf.Dataset(calibration_X, transform_fn)
    quantized_model = nncf.quantize(fp32_model, calibration_dataset, subset_size=len(calibration_X))

    ov.save_model(quantized_model, int8_ir_path, compress_to_fp16=False)
    print("Saved INT8 model ->", int8_ir_path)
    return int8_ir_path


def _time_ov_model(compiled_model, output, X, n_warmup=N_WARMUP, n_timed=N_TIMED):
    for i in range(n_warmup):
        compiled_model([X[i % len(X)]])[output]

    start = time.perf_counter()
    for i in range(n_timed):
        compiled_model([X[i % len(X)]])[output]
    elapsed = time.perf_counter() - start
    return elapsed / n_timed * 1e6  # microseconds/call


def benchmark_latency(fp32_ir_path, int8_ir_path, n_trials=7):
    """
    يكرر القياس عدة مرات ويرجع كل التجارب - قياس واحد فقط كان يعطي نتيجة
    مضللة هنا (رأينا INT8 أسرع من FP32 في تجربة، وأبطأ في ثلاث غيرها لنفس
    الكود بالضبط)، فتقرير متوسط ومدى عبر عدة تجارب هو المنهج الصحيح، لا رقم
    واحد قد يكون حظًا عابرًا.
    """
    X = load_calibration_data(n=64)
    X = [row.reshape(1, -1) for row in X]

    from train_model import train_and_evaluate
    model, _ = train_and_evaluate()
    X64 = [x.astype(np.float64) for x in X]

    core = ov.Core()
    fp32_model = core.read_model(fp32_ir_path)
    config = {ov.properties.hint.inference_precision: ov.Type.f32}
    compiled_fp32 = core.compile_model(fp32_model, "CPU", config)
    int8_model = core.read_model(int8_ir_path)
    compiled_int8 = core.compile_model(int8_model, "CPU")

    trials = {"sklearn (no OpenVINO)": [], "OpenVINO FP32": [], "OpenVINO INT8 (NNCF)": []}

    for t in range(n_trials):
        for x in X64[: min(N_WARMUP, len(X64))]:
            model.predict_proba(x)
        start = time.perf_counter()
        for i in range(N_TIMED):
            model.predict_proba(X64[i % len(X64)])
        trials["sklearn (no OpenVINO)"].append((time.perf_counter() - start) / N_TIMED * 1e6)

        trials["OpenVINO FP32"].append(_time_ov_model(compiled_fp32, compiled_fp32.output(0), X))
        trials["OpenVINO INT8 (NNCF)"].append(_time_ov_model(compiled_int8, compiled_int8.output(0), X))

    return trials


def compare_accuracy(fp32_ir_path, int8_ir_path):
    """يتحقق أن الضغط لم يكسر دقة النموذج بصمت - يقارن على نفس بيانات الاختبار."""
    import pandas as pd
    from train_model import FEATURE_COLUMNS, LABEL_COLUMN
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

    df = pd.read_csv(DATA_DIR / "occupancy_training_data.csv")
    X = df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    y = df[LABEL_COLUMN].to_numpy(dtype=np.int64)

    core = ov.Core()

    def predict_all(ir_path, precision_config=None):
        model = core.read_model(ir_path)
        compiled = core.compile_model(model, "CPU", precision_config or {})
        output = compiled.output(0)
        probs = np.array([compiled([row.reshape(1, -1)])[output][0, 0] for row in X])
        return (probs >= 0.5).astype(int)

    fp32_preds = predict_all(fp32_ir_path, {ov.properties.hint.inference_precision: ov.Type.f32})
    int8_preds = predict_all(int8_ir_path)

    def report(name, preds):
        return {
            "accuracy": accuracy_score(y, preds),
            "precision": precision_score(y, preds, zero_division=0),
            "recall": recall_score(y, preds, zero_division=0),
            "f1": f1_score(y, preds, zero_division=0),
        }

    return report("FP32", fp32_preds), report("INT8", int8_preds)


if __name__ == "__main__":
    fp32_path = MODELS_DIR / "occupancy_model.xml"
    int8_path = MODELS_DIR / "occupancy_model_int8.xml"

    print("=== Quantizing (NNCF post-training, INT8) ===")
    quantize(fp32_path, int8_path)

    print("\n=== Latency: {} trials x {} timed calls each (after {} warmup) ===".format(7, N_TIMED, N_WARMUP))
    trials = benchmark_latency(fp32_path, int8_path)
    means = {}
    for name, values in trials.items():
        mean = sum(values) / len(values)
        means[name] = mean
        print("  {:<24s}: mean {:6.2f} µs/call  (range {:.2f}-{:.2f} across {} trials)".format(
            name, mean, min(values), max(values), len(values)))

    print("\n  OpenVINO FP32 vs sklearn : {:.2f}x".format(means["sklearn (no OpenVINO)"] / means["OpenVINO FP32"]))
    print("  OpenVINO INT8 vs FP32    : {:.2f}x".format(means["OpenVINO FP32"] / means["OpenVINO INT8 (NNCF)"]))

    print("\n=== Accuracy: FP32 vs INT8 (same test rows, did quantization cost anything?) ===")
    fp32_metrics, int8_metrics = compare_accuracy(fp32_path, int8_path)
    for name, metrics in [("FP32", fp32_metrics), ("INT8", int8_metrics)]:
        print("  {}: ".format(name) + ", ".join("{}={:.3f}".format(k, v) for k, v in metrics.items()))
