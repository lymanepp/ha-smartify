"""Shared types for the two ways a controller can be configured.

Split out from `__init__.py` so that `smartify_controller.py` and the
controller subclasses can import `SmartifyEntrySource` for accurate type
hints without creating a circular import (they're imported *by*
`__init__.py`, so they can't import back from it).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry


@dataclass
class YamlControllerEntry:
    """Stand-in for a ConfigEntry, used for YAML-configured controllers.

    Controllers (`SmartifyController` and subclasses) and entities
    (`SmartifyEntity`) only read `.data`, `.options`, `.entry_id`, and `.title`
    from this object. They never touch `hass.config_entries`, so this plain
    object is a complete,
    duck-typed substitute for a real `ConfigEntry`, which lets a YAML
    controller reuse every controller/entity class unmodified while never
    being registered as a config entry (no entry shows up in the UI, nothing
    is written to `.storage/core.config_entries`, and there is no options
    flow for it -- editing it means editing YAML and reloading/restarting).
    """

    entry_id: str
    title: str
    data: Mapping[str, Any]
    options: Mapping[str, Any] = field(default_factory=dict)


# Either a real config entry (UI-created) or the YAML stand-in above -- the
# only two things a controller constructor or `SmartifyEntity` ever see.
# This is what "config_entry" parameters are actually typed as throughout
# the controller/entity layer; using the real generic `ConfigEntry[...]`
# alias here would need `SmartifyController`, which would import this
# module, which would be circular.
type SmartifyEntrySource = ConfigEntry | YamlControllerEntry
