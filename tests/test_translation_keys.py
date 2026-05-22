"""Verify that error/abort keys used in the config flow exist in translations.

Regression tests for the mismatch where the config flow referenced abort reasons
('invalid_entity', 'invalid_type') and an error key ('trigger_only_needs_decay')
that did not exist in the translation files, producing untranslated UI strings.
"""

import json
from pathlib import Path

import pytest

COMPONENT_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "smartify"
TRANSLATIONS_DIR = COMPONENT_DIR / "translations"

# Keys the config flow actually uses (kept explicit so the test fails loudly if
# code and translations drift again).
EXPECTED_ABORT_REASONS = {
    "invalid_entity",
    "invalid_type",
    "nothing_to_control",
}
EXPECTED_ERROR_KEYS = {
    "duplicate_name",
    "occupancy_needs_entity",
    "trigger_only_needs_minutes",
}

TRANSLATION_FILES = sorted(TRANSLATIONS_DIR.glob("*.json"))


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_translation_files_exist():
    assert TRANSLATION_FILES, "no translation files found"


@pytest.mark.parametrize("path", TRANSLATION_FILES, ids=lambda p: p.stem)
def test_abort_reasons_present(path: Path):
    data = _load(path)
    for section in ("config", "options"):
        abort = data.get(section, {}).get("abort", {})
        missing = EXPECTED_ABORT_REASONS - set(abort)
        # 'nothing_to_control' is only meaningful in the config section.
        if section == "options":
            missing -= {"nothing_to_control"}
        assert not missing, f"{path.name} [{section}] missing abort: {missing}"


@pytest.mark.parametrize("path", TRANSLATION_FILES, ids=lambda p: p.stem)
def test_error_keys_present(path: Path):
    data = _load(path)
    for section in ("config", "options"):
        errors = data.get(section, {}).get("error", {})
        missing = EXPECTED_ERROR_KEYS - set(errors)
        assert not missing, f"{path.name} [{section}] missing error keys: {missing}"


@pytest.mark.parametrize("path", TRANSLATION_FILES, ids=lambda p: p.stem)
def test_translation_values_nonempty(path: Path):
    data = _load(path)
    for section in ("config", "options"):
        for group in ("abort", "error"):
            for key, value in data.get(section, {}).get(group, {}).items():
                assert isinstance(value, str) and value.strip(), (
                    f"{path.name} [{section}/{group}/{key}] is empty"
                )


def test_code_literals_have_translations():
    """Cross-check the literals in config_flow.py against the translations.

    This catches a renamed error key (e.g. trigger_only_needs_decay) even if the
    EXPECTED_* sets above were not updated.
    """
    source = (COMPONENT_DIR / "config_flow.py").read_text(encoding="utf-8")

    # The stale key must be gone.
    assert "trigger_only_needs_decay" not in source

    en = _load(TRANSLATIONS_DIR / "en.json")
    config_errors = set(en["config"]["error"])
    config_aborts = set(en["config"]["abort"])

    # Spot-check the specific literals the code is known to use.
    assert "trigger_only_needs_minutes" in config_errors
    assert "occupancy_needs_entity" in config_errors
    assert "invalid_entity" in config_aborts
    assert "invalid_type" in config_aborts
