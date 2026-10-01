#!/usr/bin/env python3
"""Offline portable self-test. All generated outputs live in temporary directories."""
import sys
from pathlib import Path
import unittest

if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    suite = unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
