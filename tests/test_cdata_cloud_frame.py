"""Regression checks for remote and local cdata polling frames."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock


def _load_poll_method():
    """Load the production poll method without Home Assistant dependencies."""
    path = (
        Path(__file__).parents[1]
        / "custom_components/deltadore_tydom/tydom/tydom_client.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"))
    client = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "TydomClient"
    )
    method = next(
        node
        for node in client.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "get_poll_device_data"
    )
    module = ast.Module(body=[method], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "asyncio": asyncio,
        "_CDATA_POLL_RESPONSE_TIMEOUT": 1,
        "LOGGER": MagicMock(),
        "sanitize_log_message": str,
    }
    exec(compile(module, str(path), "exec"), namespace)
    return namespace["get_poll_device_data"]


class CdataFramingTests(IsolatedAsyncioTestCase):
    """Verify cdata framing without contacting a gateway."""

    async def test_local_and_remote_cdata_keep_the_connection_prefix(self):
        """The same cdata request has the mediation byte only in cloud mode."""
        method = _load_poll_method()
        url = "/devices/20/endpoints/10/cdata?name=energyIndex&dest=ELEC_TOTAL&reset=false"
        request = b"GET request bytes"
        for prefix in (b"", b"\x02"):
            with self.subTest(prefix=prefix):
                done = asyncio.Event()
                done.set()
                handler = SimpleNamespace(
                    prepare_request=MagicMock(return_value=("tx", request)),
                    register_cdata_poll=MagicMock(return_value=done),
                    remove_cdata_poll=MagicMock(),
                )
                client = SimpleNamespace(
                    _cmd_prefix=prefix, _message_handler=handler, send_bytes=AsyncMock()
                )
                await method(client, url)
                handler.prepare_request.assert_called_once()
                handler.register_cdata_poll.assert_called_once_with("tx")
                client.send_bytes.assert_awaited_once_with(prefix + request)
                handler.remove_cdata_poll.assert_called_once_with("tx")

    async def test_non_cdata_poll_keeps_normal_message_path(self):
        """Regular device data polling is unchanged."""
        method = _load_poll_method()
        client = SimpleNamespace(send_message=AsyncMock())
        await method(client, "/devices/20/endpoints/10/data")
        client.send_message.assert_awaited_once_with(
            method="GET", msg="/devices/20/endpoints/10/data"
        )
