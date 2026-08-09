"""Load the integration's pure-Python modules without importing Home Assistant.

``custom_components/bike_tracker/__init__.py`` pulls in Home Assistant, which
is not a test dependency. We therefore register the directory as a synthetic
package ``bt`` whose ``__init__`` is empty, so that ``import bt.tracker`` and
the relative imports inside it resolve normally.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG_DIR = ROOT / "custom_components" / "bike_tracker"

if "bt" not in sys.modules:
    package = types.ModuleType("bt")
    package.__path__ = [str(PKG_DIR)]
    package.__package__ = "bt"
    spec = importlib.util.spec_from_loader("bt", loader=None, is_package=True)
    spec.submodule_search_locations = [str(PKG_DIR)]
    package.__spec__ = spec
    sys.modules["bt"] = package
