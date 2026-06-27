# tests/unit/test_validation_metrics.py
import numpy as np
from src.pipeline.validate import compute_metrics


def test_perfect_classifier():
    y_true = np.array([1, 1, 0, 0])
    y_pred = np.array([1, 1, 0, 0])
    m = compute_metrics(y_true, y_pred)
    assert m["precision"] == 1.0
    assert m["recall"] == 1.0
    assert m["f1"] == 1.0
    assert m["accuracy"] == 1.0


def test_all_false_positives():
    y_true = np.array([0, 0, 0, 0])
    y_pred = np.array([1, 1, 1, 1])
    m = compute_metrics(y_true, y_pred)
    assert m["precision"] == 0.0
    assert m["recall"] == 0.0
    assert m["f1"] == 0.0


def test_all_false_negatives():
    y_true = np.array([1, 1, 1, 1])
    y_pred = np.array([0, 0, 0, 0])
    m = compute_metrics(y_true, y_pred)
    assert m["precision"] == 0.0
    assert m["recall"] == 0.0
    assert m["f1"] == 0.0


def test_mixed_results():
    y_true = np.array([1, 1, 0, 0])
    y_pred = np.array([1, 0, 1, 0])
    m = compute_metrics(y_true, y_pred)
    assert m["tp"] == 1
    assert m["fp"] == 1
    assert m["fn"] == 1
    assert m["tn"] == 1
    assert m["precision"] == 0.5
    assert m["recall"] == 0.5


def test_f1_harmonic_mean():
    y_true = np.array([1, 1, 1, 0])
    y_pred = np.array([1, 1, 0, 0])
    m = compute_metrics(y_true, y_pred)
    expected_f1 = 2 * m["precision"] * m["recall"] / (m["precision"] + m["recall"])
    assert abs(m["f1"] - expected_f1) < 1e-3