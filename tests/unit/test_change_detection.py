# tests/unit/test_change_detection.py
import numpy as np
import pytest
from src.pipeline.change import (
    compute_log_ratio,
    compute_combined_magnitude,
    apply_burn_mask,
    remove_small_patches,
)


def test_log_ratio_positive_for_decrease():
    # Post backscatter lower than pre — should produce positive change
    pre = np.array([[5.0, 5.0], [5.0, 5.0]], dtype=np.float32)
    post = np.array([[2.0, 2.0], [2.0, 2.0]], dtype=np.float32)
    result = compute_log_ratio(pre, post)
    assert np.all(result < 0)


def test_log_ratio_zero_for_no_change():
    arr = np.array([[5.0, 5.0]], dtype=np.float32)
    result = compute_log_ratio(arr, arr)
    assert np.all(result == 0.0)


def test_combined_magnitude_always_positive():
    vv = np.array([[-3.0, 2.0], [0.0, -1.0]], dtype=np.float32)
    vh = np.array([[1.0, -2.0], [-1.0, 0.0]], dtype=np.float32)
    result = compute_combined_magnitude(vv, vh)
    assert np.all(result >= 0)


def test_combined_magnitude_formula():
    vv = np.array([[3.0]], dtype=np.float32)
    vh = np.array([[4.0]], dtype=np.float32)
    result = compute_combined_magnitude(vv, vh)
    assert abs(result[0, 0] - 5.0) < 1e-5


def test_burn_mask_threshold():
    combined = np.array([[1.0, 3.0], [5.0, 2.9]], dtype=np.float32)
    mask = apply_burn_mask(combined, threshold=3.0)
    assert mask[0, 0] == 0  # below threshold
    assert mask[0, 1] == 1  # at threshold
    assert mask[1, 0] == 1  # above threshold
    assert mask[1, 1] == 0  # below threshold


def test_burn_mask_all_zeros_below_threshold():
    combined = np.ones((5, 5), dtype=np.float32) * 2.0
    mask = apply_burn_mask(combined, threshold=3.0)
    assert np.all(mask == 0)


def test_remove_small_patches_removes_isolated_pixels():
    mask = np.zeros((10, 10), dtype=np.uint8)
    mask[5, 5] = 1  # single isolated pixel
    result = remove_small_patches(mask, min_pixels=5)
    assert result[5, 5] == 0


def test_remove_small_patches_keeps_large_patches():
    mask = np.zeros((10, 10), dtype=np.uint8)
    mask[2:7, 2:7] = 1  # 5x5 = 25 pixel patch
    result = remove_small_patches(mask, min_pixels=5)
    assert np.sum(result) == 25