"""Smoke test: the package installs and imports in the locked environment."""

import eaidrs


def test_package_imports_with_version() -> None:
    assert eaidrs.__version__ == "0.1.0"
