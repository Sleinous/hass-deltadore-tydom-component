"""Tests for the alarm action that uses the integration's stored PIN."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase


class _HomeAssistantError(Exception):
    """Stand-in for Home Assistant's user-facing error."""


def _load_stored_pin_action():
    """Load only the alarm action method without importing Home Assistant."""
    source_path = (
        Path(__file__).parents[1]
        / "custom_components"
        / "deltadore_tydom"
        / "ha_entities.py"
    )
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    alarm_node = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "HaAlarm"
    )
    method = next(
        node
        for node in alarm_node.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "async_set_mode_using_stored_pin"
    )
    isolated_module = ast.Module(
        body=[
            ast.ClassDef(
                name="Harness", bases=[], keywords=[], body=[method], decorator_list=[]
            )
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(isolated_module)
    namespace = {"HomeAssistantError": _HomeAssistantError}
    exec(compile(isolated_module, source_path, "exec"), namespace)
    return namespace["Harness"].async_set_mode_using_stored_pin


_SET_MODE_USING_STORED_PIN = _load_stored_pin_action()


class _Harness:
    """Minimal alarm entity for testing the stored-PIN action routing."""

    async_set_mode_using_stored_pin = _SET_MODE_USING_STORED_PIN

    def __init__(self, pin: str | None = "123456") -> None:
        self._device = SimpleNamespace(_tydom_client=SimpleNamespace(_alarm_pin=pin))
        self.calls: list[tuple[str, str | None]] = []

    async def async_alarm_disarm(self, code=None) -> None:
        self.calls.append(("disarm", code))

    async def async_alarm_arm_away(self, code=None) -> None:
        self.calls.append(("away", code))

    async def async_alarm_arm_home(self, code=None) -> None:
        self.calls.append(("home", code))

    async def async_alarm_arm_night(self, code=None) -> None:
        self.calls.append(("night", code))


class AlarmStoredPinActionTests(IsolatedAsyncioTestCase):
    """Ensure the automation action reuses existing alarm commands safely."""

    async def test_each_mode_uses_existing_alarm_method_without_ui_code(self) -> None:
        """No code is requested from the action; the client supplies its PIN."""
        for mode in ("disarm", "away", "home", "night"):
            entity = _Harness()

            await entity.async_set_mode_using_stored_pin(mode)

            self.assertEqual(entity.calls, [(mode, None)])

    async def test_action_requires_a_configured_pin(self) -> None:
        """Do not send an alarm command when the integration PIN is absent."""
        entity = _Harness(pin=None)

        with self.assertRaises(_HomeAssistantError):
            await entity.async_set_mode_using_stored_pin("away")

        self.assertEqual(entity.calls, [])

    async def test_action_rejects_unknown_modes(self) -> None:
        """Reject invalid mode values even if called outside the service schema."""
        entity = _Harness()

        with self.assertRaises(_HomeAssistantError):
            await entity.async_set_mode_using_stored_pin("trigger")

        self.assertEqual(entity.calls, [])
