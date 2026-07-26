"""Tests for temporary shutter movement polling."""

import importlib.util
from pathlib import Path
import sys
import types
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock

_MISSING = object()
_original_modules: dict[str, object] = {}


def _module(name: str, **attributes) -> types.ModuleType:
    """Install a minimal module required to load shutter devices."""
    _original_modules.setdefault(name, sys.modules.get(name, _MISSING))
    module = types.ModuleType(name)
    for attribute, value in attributes.items():
        setattr(module, attribute, value)
    sys.modules[name] = module
    return module


for package_name in (
    "custom_components",
    "custom_components.deltadore_tydom",
    "custom_components.deltadore_tydom.tydom",
):
    package = _module(package_name)
    package.__path__ = []

_module(
    "custom_components.deltadore_tydom.const",
    LOGGER=MagicMock(),
    validate_value_with_metadata=MagicMock(return_value=(True, None)),
)

module_name = "custom_components.deltadore_tydom.tydom.tydom_devices"
module_path = (
    Path(__file__).parents[1]
    / "custom_components"
    / "deltadore_tydom"
    / "tydom"
    / "tydom_devices.py"
)
spec = importlib.util.spec_from_file_location(module_name, module_path)
assert spec is not None and spec.loader is not None
devices_module = importlib.util.module_from_spec(spec)
_original_modules.setdefault(module_name, sys.modules.get(module_name, _MISSING))
sys.modules[module_name] = devices_module
spec.loader.exec_module(devices_module)
TydomShutter = devices_module.TydomShutter

for name, original in _original_modules.items():
    if original is _MISSING:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = original


class TestShutterPolling(IsolatedAsyncioTestCase):
    """Verify shutter commands start a bounded refresh burst."""

    def _shutter(self):
        client = MagicMock()
        client.put_devices_data = AsyncMock()
        client.activate_device_polling = MagicMock()
        shutter = TydomShutter(
            client,
            "20_10",
            "10",
            "Shutter",
            "shutter",
            "20",
            {"position": {"permission": "rw"}},
            {"position": 0},
        )
        return shutter, client

    async def test_movement_commands_start_active_polling(self) -> None:
        """Opening and closing request the standard movement window."""
        shutter, client = self._shutter()

        await shutter.up()
        await shutter.down()

        self.assertEqual(client.activate_device_polling.call_count, 2)
        client.activate_device_polling.assert_called_with("10", "20", duration=30.0)

    async def test_set_position_starts_active_polling(self) -> None:
        """A target position command also needs intermediate feedback."""
        shutter, client = self._shutter()

        await shutter.set_position(75)

        client.put_devices_data.assert_awaited_once_with("10", "20", "position", "75")
        client.activate_device_polling.assert_called_once_with(
            "10", "20", duration=30.0
        )

    async def test_stop_shortens_active_polling(self) -> None:
        """STOP keeps a short window for the final settled position."""
        shutter, client = self._shutter()

        await shutter.stop()

        client.activate_device_polling.assert_called_once_with("10", "20", duration=5.0)
