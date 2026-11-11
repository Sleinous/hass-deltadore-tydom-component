"""TYWATT 2000 cmeta profile from issue #550, with anonymous identifiers."""

from unittest import IsolatedAsyncioTestCase
from unittest.mock import MagicMock

from test_protocol_responses import MessageHandler, handler_module


class Tywatt2000CmetaTests(IsolatedAsyncioTestCase):
    """Preserve current polling without starving live energy requests."""

    async def test_advertised_profile_registers_live_commands_only(self):
        """The reported mixed cmeta profile schedules 10 live requests."""
        handler_module.device_command_metadata.clear()
        client = MagicMock()
        handler = MessageHandler(client, b"")
        destinations = [
            "ELEC_TOTAL",
            "ELEC_OUTLET",
            "ELEC_OTHER",
            "UNDEF_HEATING",
            "UNDEF_HOTWATER",
            "TEMP_INDOOR",
            "TEMP_OUTDOOR",
        ]
        metadata = [
            {
                "name": "energyHisto",
                "parameters": [{"name": "dest", "enum_values": destinations}],
            },
            {
                "name": "energyDistrib",
                "parameters": [{"name": "src", "enum_values": ["ELEC", "UNDEF"]}],
            },
            {
                "name": "energyInstant",
                "parameters": [{"name": "unit", "enum_values": ["ELEC_A"]}],
            },
            {
                "name": "energyIndex",
                "parameters": [{"name": "dest", "enum_values": destinations}],
            },
        ]
        await handler.parse_cmeta_data(
            [{"id": 20, "endpoints": [{"id": 10, "cmetadata": metadata}]}],
            "transaction",
        )
        urls = [call.args[0] for call in client.add_poll_device_url_5m.call_args_list]
        self.assertEqual(len(urls), 10)
        self.assertTrue(any("name=energyInstant&unit=ELEC_A" in url for url in urls))
        self.assertTrue(any("name=energyIndex&dest=ELEC_TOTAL" in url for url in urls))
        self.assertEqual(sum("name=energyDistrib" in url for url in urls), 2)
        self.assertFalse(any("name=energyHisto" in url for url in urls))
