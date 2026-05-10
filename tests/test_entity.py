from unittest.mock import MagicMock

from custom_components.smartify.entity import SmartifyEntity


def make_controller():
    controller = MagicMock()
    controller.name = "Test Controller"
    controller.available = True

    controller.extra_state_attributes = {
        "mode": "auto",
    }

    controller.config_entry.entry_id = "entry-123"

    return controller


def test_entity_instantiates():
    controller = make_controller()

    entity = SmartifyEntity(controller)

    assert entity is not None


def test_entity_has_controller_reference():
    controller = make_controller()

    entity = SmartifyEntity(controller)

    assert entity.controller is controller


def test_entity_unique_id():
    controller = make_controller()

    entity = SmartifyEntity(controller)

    assert entity.unique_id == ("entry-123")


def test_entity_available_true():
    controller = make_controller()

    entity = SmartifyEntity(controller)

    assert entity.available is True
