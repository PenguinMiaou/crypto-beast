"""Verify no naive datetime.utcnow() usage in production code."""
import os


def test_no_utcnow_in_production_code():
    root = os.path.dirname(os.path.dirname(__file__))
    violations = []
    for dirpath, _, filenames in os.walk(root):
        if "tests" in dirpath or ".venv" in dirpath or "__pycache__" in dirpath:
            continue
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            path = os.path.join(dirpath, fname)
            try:
                with open(path, encoding="utf-8", errors="ignore") as f:
                    source = f.read()
            except (OSError, IOError):
                continue
            if "utcnow()" in source:
                violations.append(os.path.relpath(path, root))
    assert violations == [], f"datetime.utcnow() found in: {violations}"
