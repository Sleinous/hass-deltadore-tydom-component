"""Tests for rate-limited endpoint error logging."""

import importlib.util
from pathlib import Path
import sys
import types
from unittest import IsolatedAsyncioTestCase
from unittest.mock import MagicMock, patch


_MISSING = object()
_original_modules: dict[str, object] = {}


def _module(name: str, **attributes) -> types.ModuleType:
    """Install a minimal module needed to load the protocol code in isolation."""
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

logger = MagicMock()
_module(
    "custom_components.deltadore_tydom.const",
    LOGGER=logger,
    validate_value_with_metadata=MagicMock(return_value=(True, None)),
)

root = Path(__file__).parents[1]
tydom_path = root / "custom_components" / "deltadore_tydom" / "tydom"

devices_spec = importlib.util.spec_from_file_location(
    "custom_components.deltadore_tydom.tydom.tydom_devices",
    tydom_path / "tydom_devices.py",
)
assert devices_spec is not None and devices_spec.loader is not None
devices_module = importlib.util.module_from_spec(devices_spec)
_original_modules.setdefault(
    devices_spec.name, sys.modules.get(devices_spec.name, _MISSING)
)
sys.modules[devices_spec.name] = devices_module
devices_spec.loader.exec_module(devices_module)

handler_spec = importlib.util.spec_from_file_location(
    "custom_components.deltadore_tydom.tydom.MessageHandler",
    tydom_path / "MessageHandler.py",
)
assert handler_spec is not None and handler_spec.loader is not None
handler_module = importlib.util.module_from_spec(handler_spec)
_original_modules.setdefault(
    handler_spec.name, sys.modules.get(handler_spec.name, _MISSING)
)
sys.modules[handler_spec.name] = handler_module
handler_spec.loader.exec_module(handler_module)

MessageHandler = handler_module.MessageHandler

for name, original in _original_modules.items():
    if original is _MISSING:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = original


class EndpointErrorTests(IsolatedAsyncioTestCase):
    """Exercise transient, persistent, and recovered endpoint errors."""

    def setUp(self) -> None:
        """Reset parser registries and logging before every test."""
        logger.reset_mock()
        handler_module.device_name.clear()
        handler_module.device_type.clear()
        handler_module.device_endpoint.clear()
        handler_module.device_metadata.clear()
        handler_module.device_name["10_20"] = "Terrace light"
        handler_module.device_type["10_20"] = "light"
        handler_module.device_metadata["10_20"] = {}
        self.handler = MessageHandler(MagicMock(), b"")

    @staticmethod
    def _response(error: int, with_data: bool = True) -> list[dict]:
        """Build one endpoint response."""
        endpoint = {"id": 10, "error": error}
        if with_data:
            endpoint["data"] = [
                {
                    "name": "level",
                    "value": 0,
                    "validity": "upToDate",
                }
            ]
        return [{"id": 20, "endpoints": [endpoint]}]

    async def test_single_error_with_data_is_reported_at_info(self) -> None:
        """Keep issue-report evidence without entering the warning panel."""
        devices = await self.handler.parse_devices_data(self._response(1), None)

        logger.warning.assert_not_called()
        self.assertEqual(logger.info.call_count, 1)
        self.assertEqual(logger.info.call_args.args[5], 1)
        self.assertFalse(hasattr(devices[0], "level"))
        self.assertEqual(
            self.handler._endpoint_errors[(20, 10)].occurrences,
            1,
        )

    async def test_transient_error_remains_visible_across_recoveries(self) -> None:
        """Every incident and recovery from a flapping endpoint remains visible."""
        await self.handler.parse_devices_data(self._response(1), None)
        await self.handler.parse_devices_data(self._response(0), None)
        await self.handler.parse_devices_data(self._response(1), None)

        endpoint_error_calls = [
            call
            for call in logger.info.call_args_list
            if call.args and call.args[0].startswith("Endpoint error")
        ]
        recovery_calls = [
            call
            for call in logger.info.call_args_list
            if call.args and call.args[0].startswith("Endpoint recovered:")
        ]
        self.assertEqual(len(endpoint_error_calls), 2)
        self.assertEqual(len(recovery_calls), 1)

    async def test_persistent_error_warns_with_occurrence_count(self) -> None:
        """The third consecutive error is promoted with its count."""
        with patch.object(
            handler_module.time,
            "monotonic",
            side_effect=[100.0, 101.0, 102.5],
        ):
            for _ in range(3):
                await self.handler.parse_devices_data(self._response(1), None)

        logger.warning.assert_called_once_with(
            "Endpoint error%s: device_id=%s, endpoint_id=%s, error=%s, "
            "consecutive_occurrences=%s, duration=%.1fs; retaining previous state",
            " persists",
            20,
            10,
            1,
            3,
            2.5,
        )

    async def test_persistent_error_warning_is_rate_limited(self) -> None:
        """Continuing errors warn only at the configured milestones."""
        for _ in range(10):
            await self.handler.parse_devices_data(self._response(1), None)

        self.assertEqual(logger.warning.call_count, 2)
        warning_counts = [call.args[5] for call in logger.warning.call_args_list]
        self.assertEqual(warning_counts, [3, 10])

    async def test_error_without_data_warns_immediately(self) -> None:
        """A response with neither usable data nor success warns on occurrence one."""
        await self.handler.parse_devices_data(
            self._response(1, with_data=False),
            None,
        )

        self.assertEqual(logger.warning.call_count, 1)
        self.assertEqual(logger.warning.call_args.args[5], 1)
        logger.info.assert_not_called()

    async def test_success_resets_counter_and_updates_state(self) -> None:
        """A successful response closes the incident and processes fresh data."""
        await self.handler.parse_devices_data(self._response(1), None)
        devices = await self.handler.parse_devices_data(self._response(0), None)

        self.assertNotIn((20, 10), self.handler._endpoint_errors)
        self.assertEqual(devices[0].level, 0)
        recovery_calls = [
            call
            for call in logger.info.call_args_list
            if call.args and call.args[0].startswith("Endpoint recovered:")
        ]
        self.assertEqual(len(recovery_calls), 1)
        self.assertEqual(recovery_calls[0].args[4], 1)

    async def test_unknown_usage_remains_visible_and_keeps_generic_sensor(self) -> None:
        """Every unsupported usage remains visible for useful issue reports."""
        first = await self.handler.get_device(
            MagicMock(),
            "newUnsupportedUsage",
            "10_20",
            20,
            "Future device",
            10,
            None,
        )
        second = await self.handler.get_device(
            MagicMock(),
            "newUnsupportedUsage",
            "11_21",
            21,
            "Another future device",
            11,
            None,
        )

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(logger.info.call_count, 2)
        logger.info.assert_called_with(
            "Unsupported Tydom usage '%s'; creating a generic sensor "
            "(device_id=%s, uid=%s). Report this usage if dedicated "
            "device support is missing.",
            "newUnsupportedUsage",
            21,
            "11_21",
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
