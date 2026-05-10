from pathlib import Path
import sys
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


pytest_plugins = [
    "pytest_homeassistant_custom_component",
]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations,
):
    """Automatically enable loading custom integrations."""
    yield


@pytest.fixture(autouse=True)
def suppress_entity_sw_version_patch(monkeypatch):
    monkeypatch.setattr(
        "custom_components.smartify.entity.SmartifyEntity._set_sw_version",
        AsyncMock(),
    )
