"""Shared fixtures for the CrewAI content-generator test suite.

All tests run without real API calls.  Heavy external libs (requests,
selenium, google.generativeai) are patched at import time via autouse
fixtures so individual test modules don't need to repeat the boilerplate.
"""

import sys
import threading
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

SRC_DIR = Path(__file__).parent.parent / "src"


@pytest.fixture(autouse=False)
def no_real_requests(mocker):
    """Block accidental HTTP calls in any test that uses this fixture."""
    mocker.patch("requests.get", side_effect=RuntimeError("No real HTTP in tests"))
    mocker.patch("requests.post", side_effect=RuntimeError("No real HTTP in tests"))


# ---------------------------------------------------------------------------
# Minimal valid TechSpecsOutput payload (re-used across schema tests)
# ---------------------------------------------------------------------------

MINIMAL_TECH_SPECS = {
    "Technical_Specifications": {
        "Printing": {"Print Speed": "600 mm/s", "Layer Height": "0.05-0.35 mm"},
        "Build Volume": {"X": "300 mm", "Y": "300 mm", "Z": "300 mm"},
    },
    "Key_Features": [
        {"feature_name": "Speed", "spec_value": "600 mm/s", "benefit": "Fast prints"},
        {"feature_name": "Volume", "spec_value": "300×300×300 mm", "benefit": "Large parts"},
        {"feature_name": "Temp", "spec_value": "300 °C", "benefit": "Exotic filaments"},
    ],
    "Marketing_Content": "The Bambu X1 Carbon is the pinnacle of desktop FDM printing.",
}


@pytest.fixture
def minimal_tech_specs():
    """Return a copy of the minimal valid TechSpecsOutput dict."""
    return dict(MINIMAL_TECH_SPECS)
