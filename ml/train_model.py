# -*- coding: utf-8 -*-
"""
سراب - المرحلة الرابعة: تدريب نموذج توقّع الإشغال وتصديره

يدرّب انحدارًا لوجستيًا (LogisticRegression) على occupancy_training_data.csv
الناتج من build_training_data.py، يقيّمه بصدق (accuracy + precision/recall
لأن الفئات غير متوازنة ~21% إشغال)، ثم يصدّره إلى ONNX ويحوّله إلى صيغة
OpenVINO IR الجاهزة للتشغيل عبر OpenVINO Runtime.

الترتيب الثابت للميزات (يجب أن يطابقه predictor.py تمامًا):
    [hour, is_weekend, prev_occupied,
     pattern_classroom, pattern_corridor, pattern_critical, pattern_office]
"""

import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sklearn.model_selection import train_test_split

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
MODELS_DIR = REPO_ROOT / "models"

HOUR_COLUMNS = ["hour_{}".format(h) for h in range(24)]
FEATURE_COLUMNS = (
    ["is_weekend", "prev_occupied"]
    + HOUR_COLUMNS
    + ["pattern_classroom", "pattern_corridor", "pattern_critical", "pattern_office"]
)
LABEL_COLUMN = "next_occupied"


def load_xy(path=None):
    if path is None:
        path = DATA_DIR / "occupancy_training_data.csv"
    df = pd.read_csv(path)
    X = df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    y = df[LABEL_COLUMN].to_numpy(dtype=np.int64)
    return X, y


def train_and_evaluate():
    X, y = load_xy()
    # stratify: نحافظ على نفس نسبة عدم التوازن في التدريب والاختبار
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    model = LogisticRegression(max_iter=1000)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    metrics = {
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred, zero_division=0),
        "recall": recall_score(y_test, y_pred, zero_division=0),
        "f1": f1_score(y_test, y_pred, zero_division=0),
    }

    print("=== تقييم صادق على بيانات اختبار لم يرها النموذج أثناء التدريب ===")
    for k, v in metrics.items():
        print("  {:<10s}: {:.3f}".format(k, v))
    print()
    print("معامِلات النموذج (تفسير مباشر - كل معامل يمثل تأثير ميزته):")
    for name, coef in zip(FEATURE_COLUMNS, model.coef_[0]):
        print("  {:<20s}: {:+.3f}".format(name, coef))
    print("  {:<20s}: {:+.3f}".format("(intercept)", model.intercept_[0]))

    return model, metrics


def export_to_onnx(model, onnx_path=None):
    if onnx_path is None:
        onnx_path = MODELS_DIR / "occupancy_model.onnx"
    # NOTE: skl2onnx's standard classifier export uses ai.onnx.ml ops
    # (LinearClassifier / ZipMap). OpenVINO's ONNX frontend supports neither
    # ("No conversion rule found for operations: ai.onnx.ml.LinearClassifier").
    # LogisticRegression is just sigmoid(X @ W.T + b), so we build that graph
    # by hand with only core ai.onnx ops (Gemm + Sigmoid), which OpenVINO
    # converts cleanly.
    import onnx
    from onnx import helper, numpy_helper, TensorProto

    n_features = len(FEATURE_COLUMNS)
    W = model.coef_.astype(np.float32)          # shape (1, n_features)
    b = model.intercept_.astype(np.float32)      # shape (1,)

    X = helper.make_tensor_value_info("X", TensorProto.FLOAT, [None, n_features])
    probability = helper.make_tensor_value_info("probability", TensorProto.FLOAT, [None, 1])

    W_init = numpy_helper.from_array(W, name="W")
    b_init = numpy_helper.from_array(b, name="b")

    gemm_node = helper.make_node(
        "Gemm", inputs=["X", "W", "b"], outputs=["logits"],
        alpha=1.0, beta=1.0, transB=1,  # computes X @ W.T + b
    )
    sigmoid_node = helper.make_node("Sigmoid", inputs=["logits"], outputs=["probability"])

    graph = helper.make_graph(
        [gemm_node, sigmoid_node],
        "occupancy_logreg",
        [X], [probability],
        initializer=[W_init, b_init],
    )
    onnx_model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    onnx.checker.check_model(onnx_model)

    MODELS_DIR.mkdir(exist_ok=True)
    with open(onnx_path, "wb") as f:
        f.write(onnx_model.SerializeToString())
    print("\nSaved ONNX model ->", onnx_path)
    return onnx_path


def convert_to_openvino(onnx_path=None, ir_path=None):
    if onnx_path is None:
        onnx_path = MODELS_DIR / "occupancy_model.onnx"
    if ir_path is None:
        ir_path = MODELS_DIR / "occupancy_model.xml"
    import openvino as ov

    ov_model = ov.convert_model(onnx_path)
    # compress_to_fp16=False: the default FP16 weight compression is meant for
    # large models where file size matters; for our ~30-float model it buys
    # nothing and was measurably shifting predicted probabilities (~1e-3),
    # which matters more than file size here.
    ov.save_model(ov_model, ir_path, compress_to_fp16=False)
    print("Saved OpenVINO IR ->", ir_path, "(+ .bin alongside it)")
    return ir_path


if __name__ == "__main__":
    model, metrics = train_and_evaluate()
    onnx_path = export_to_onnx(model)
    ir_path = convert_to_openvino(onnx_path)
