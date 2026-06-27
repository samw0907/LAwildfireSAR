# tests/unit/test_config.py
import pytest
from scripts.validate_config import validate_config


def test_config_validates_successfully():
    # Should not raise
    validate_config()