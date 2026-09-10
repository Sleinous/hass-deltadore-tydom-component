"""Tests for gateway-level TYDOM product association."""

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import MagicMock, patch

from custom_components.deltadore_tydom.hub import (
    ASSOCIATION_CATALOG,
    GROUPABLE_ASSOCIATION_BY_LABEL,
    OFFICIAL_DISCOVERY_PROFILES,
    configure_groupable_product,
    configure_tyxia_2600_interrupter,
    get_association_choices,
    get_install_payload,
    remove_product_association,
    start_product_association,
)
from custom_components.deltadore_tydom.hub import Hub
from custom_components.deltadore_tydom.ha_entities import (
    HAGatewayAssociationGuideButton,
    HADeviceRemovalButton,
)
from custom_components.deltadore_tydom.official_association_tutorials import (
    OFFICIAL_ASSOCIATION_TUTORIALS,
    get_association_illustration_data_url,
    get_association_illustration_layout,
    get_association_illustration_svg,
)
from custom_components.deltadore_tydom.const import DOMAIN
from custom_components.deltadore_tydom.tydom.tydom_devices import (
    TydomInterrupter,
    TydomScene,
)


class _Client:
    def __init__(self) -> None:
        self._remote_mode = False
        self.payloads: list[dict[str, str | int]] = []

    async def post_device_discovery(self, payload: dict[str, str | int]) -> None:
        self.payloads.append(payload)


class GatewayAssociationTests(IsolatedAsyncioTestCase):
    """Ensure pairing starts at the gateway, not an existing device."""

    def test_x3d_payload_omits_the_network(self) -> None:
        """X3D pairing leaves the optional network field out."""
        self.assertEqual(
            get_install_payload("opening_x3d"),
            {"protocol": "X3D", "type": "x3d_rm", "profile": "opening"},
        )

    def test_zigbee_defaults_to_the_first_network(self) -> None:
        """Zigbee uses the official application's default network."""
        self.assertEqual(
            get_install_payload("light_zigbee"),
            {"protocol": "ZIGBEE", "type": "", "profile": "light", "net": 0},
        )

    def test_unknown_profile_is_rejected_before_writing(self) -> None:
        """Reject a profile that is not an official request template."""
        with self.assertRaisesRegex(ValueError, "Unknown TYDOM"):
            get_install_payload("not-a-product")

    def test_same_radio_recipe_can_be_exposed_in_multiple_categories(self) -> None:
        """Keep usage choice separate from the protocol recipe it selects."""
        lighting = ASSOCIATION_CATALOG["Éclairages"]
        gate = ASSOCIATION_CATALOG["Portail"]

        self.assertIn(
            "official:light_X3D_x3d_rm", {choice.profile_id for choice in lighting}
        )
        self.assertIn(
            "official:light_X3D_x3d_rm", {choice.profile_id for choice in gate}
        )

    def test_catalog_matches_the_official_application_group_order(self) -> None:
        """Keep the gateway flow familiar to users of the official app."""
        self.assertEqual(
            tuple(ASSOCIATION_CATALOG),
            (
                "Volets",
                "Éclairages",
                "Thermique",
                "Garage",
                "Portail",
                "Alarme",
                "Caméras",
                "Consommation",
                "Porte",
                "Fenêtres",
                "Stores",
                "Prise",
                "Autres",
                "Télécommandes et claviers",
                "Interrupteurs",
                "Capteurs",
            ),
        )

    def test_category_change_updates_the_available_product_family(self) -> None:
        """A category controls its product list without changing the gateway."""
        tydom_hub = object.__new__(Hub)
        tydom_hub._association_controls = []
        tydom_hub._association_category = "Éclairages"
        tydom_hub._association_product = "TYXIA 4600"
        tydom_hub._association_profile = "light_x3d"

        tydom_hub.set_association_category("Volets")

        self.assertEqual(tydom_hub.association_category, "Volets")
        self.assertEqual(tydom_hub.association_product_label, "ACTIVE HOME KLINE")

    def test_tyxia_2600_exposes_each_physical_button_and_its_guide(self) -> None:
        """Present the two TYDOM flows without mixing their button sequences."""
        tydom_hub = object.__new__(Hub)
        tydom_hub._association_controls = []
        tydom_hub._association_category = "Interrupteurs"
        tydom_hub._association_product = "TYXIA 2600"
        tydom_hub._association_profile = "official:remote_X3D_direct"
        tydom_hub._association_channel = "Bouton A"

        self.assertEqual(tydom_hub.association_channel_labels, ("Bouton A", "Bouton B"))
        self.assertIn(
            "choisissez d'abord la voie à associer : Bouton A",
            tydom_hub.association_instructions[1],
        )
        self.assertIn(
            "bouton A physique pendant 6 secondes",
            tydom_hub.association_instructions[3],
        )
        self.assertIn(
            "bouton A physique pendant 3 secondes",
            tydom_hub.association_instructions[7],
        )
        self.assertIn(
            "Maintenez B pendant 3 secondes", tydom_hub.association_instructions[5]
        )
        self.assertIn(
            "voie A (Bouton A)",
            tydom_hub.association_instructions[9],
        )

        tydom_hub.set_association_channel("Bouton B")

        self.assertIn(
            "choisissez d'abord la voie à associer : Bouton B",
            tydom_hub.association_instructions[1],
        )
        self.assertIn(
            "bouton B physique pendant 6 secondes",
            tydom_hub.association_instructions[3],
        )
        self.assertIn(
            "bouton B physique pendant 3 secondes",
            tydom_hub.association_instructions[7],
        )
        self.assertIn(
            "Maintenez B pendant 3 secondes", tydom_hub.association_instructions[5]
        )
        self.assertIn(
            "voie B (Bouton B)",
            tydom_hub.association_instructions[9],
        )

    def test_tyxia_2600_exposes_its_official_visual_steps(self) -> None:
        """Keep the selected channel linked to its app-provided illustrations."""
        tydom_hub = object.__new__(Hub)
        tydom_hub._association_controls = []
        tydom_hub._association_category = "Interrupteurs"
        tydom_hub._association_product = "TYXIA 2600"
        tydom_hub._association_profile = "official:remote_X3D_direct"
        tydom_hub._association_channel = "Bouton A"

        illustrations = tydom_hub.association_illustration_ids

        self.assertEqual(len(illustrations), 5)
        self.assertEqual(illustrations[0], "catalog_switch_tyxia2600_btna_step1")
        svg = get_association_illustration_svg(illustrations[0])
        self.assertIsNotNone(svg)
        self.assertIn("<svg", svg)
        self.assertIn("<path", svg)
        inline_image = get_association_illustration_data_url(illustrations[0])
        self.assertIsNotNone(inline_image)
        self.assertTrue(inline_image.startswith("data:image/svg+xml;base64,"))

    async def test_guide_button_opens_the_frontend_dialog(self) -> None:
        """The guide control sends structured data instead of a notification."""
        bus = MagicMock()
        guide_hub = SimpleNamespace(
            hub_id="gateway",
            association_channel_label="Bouton A",
            association_product_label="TYXIA 2600",
            association_instructions=("1. Préparez le bouton A.",),
            association_illustration_layout=(
                None,
                ("catalog_switch_tyxia2600_btna_step1",),
                False,
            ),
        )
        button = object.__new__(HAGatewayAssociationGuideButton)
        button._hub = guide_hub
        button._hass = SimpleNamespace(bus=bus)

        await button.async_press()

        bus.async_fire.assert_called_once()
        event, payload = bus.async_fire.call_args.args
        self.assertEqual(event, "deltadore_tydom_association_guide")
        self.assertEqual(payload["title"], "TYXIA 2600 — guide d'association (Bouton A)")
        self.assertEqual(payload["instructions"], ["1. Préparez le bouton A."])
        self.assertEqual(len(payload["illustrations"]), 1)
        self.assertTrue(payload["illustrations"][0].startswith("data:image/svg+xml"))

    def test_tymoov_radio_exposes_only_each_official_step_visual(self) -> None:
        """Avoid presenting a catalogue thumbnail as an association instruction."""
        overview, steps, stepwise = get_association_illustration_layout("25_tymoov")

        self.assertIsNone(overview)
        self.assertTrue(stepwise)
        self.assertEqual(
            steps,
            ("catalog_25_tymoov_tuto1", "catalog_25_tymoov_tuto2"),
        )

    def test_tyxia_series_guide_omits_its_non_instructional_visuals(self) -> None:
        """Do not show the official screwdriver image as an association step."""
        overview, steps, stepwise = get_association_illustration_layout(
            "7_Tyxia_serie4000"
        )

        self.assertIsNone(overview)
        self.assertTrue(stepwise)
        self.assertEqual(steps, ())

    def test_groupable_product_is_hidden_on_an_unsupported_gateway(self) -> None:
        """Do not expose a stale multi-channel flow on TYDOM 1/2 or Hub Tyxal+."""
        tydom_hub = object.__new__(Hub)
        tydom_hub._association_controls = []
        tydom_hub._association_category = "Interrupteurs"
        tydom_hub._association_product = "TYXIA 2600"
        tydom_hub._association_profile = "official:remote_X3D_direct"
        tydom_hub._association_channel = "Bouton A"
        tydom_hub._id = "gateway"
        tydom_hub.devices = {
            "gateway": SimpleNamespace(mainReference="21800010")  # TYDOM 1.0
        }

        self.assertFalse(tydom_hub.association_product_supported)
        self.assertEqual(tydom_hub.association_channel_labels, ())
        self.assertEqual(tydom_hub.association_instructions, ())

    def test_official_products_hide_ambiguous_generic_recipes(self) -> None:
        """Known hardware must not be mixed with raw radio-profile choices."""
        self.assertEqual(
            tuple(choice.label for choice in get_association_choices("Interrupteurs")),
            ("TYXIA 2310", "TYXIA 2600", "TYXIA 2700"),
        )

    def test_product_usage_is_limited_to_the_official_catalog(self) -> None:
        """An opening detector only offers its documented door/window usages."""
        tydom_hub = object.__new__(Hub)
        tydom_hub._association_controls = []
        tydom_hub._association_category = "Porte"
        tydom_hub._association_product = "DETECTEUR OUVERTURE"
        tydom_hub._association_profile = "official:detector_X3D_direct"

        self.assertEqual(tydom_hub.association_usage_labels, ("Porte", "Fenêtres"))

        tydom_hub.set_association_usage("Fenêtres")

        self.assertEqual(tydom_hub.association_category, "Fenêtres")
        self.assertEqual(
            get_install_payload(tydom_hub._association_profile),
            {"protocol": "X3D", "type": "direct", "profile": "detector"},
        )

    def test_multi_usage_product_uses_the_recipe_for_its_selected_usage(self) -> None:
        """A product can switch between its documented HVAC and energy usages."""
        tydom_hub = object.__new__(Hub)
        tydom_hub._association_controls = []
        tydom_hub._association_category = "Thermique"
        tydom_hub._association_product = "HITACHI ATW"
        tydom_hub._association_profile = "official:thermic_X3D_x3d_rm_es"

        self.assertEqual(
            tydom_hub.association_usage_labels,
            ("Thermique", "Consommation"),
        )

        tydom_hub.set_association_usage("Consommation")

        self.assertEqual(
            get_install_payload(tydom_hub._association_profile),
            {"protocol": "X3D", "type": "direct", "profile": "typassAtl"},
        )

    def test_official_catalog_profiles_are_available_to_the_gateway(self) -> None:
        """Keep every app-derived recipe addressable by product selection."""
        self.assertGreaterEqual(len(OFFICIAL_DISCOVERY_PROFILES), 30)

    def test_every_active_official_model_has_a_tutorial_when_one_exists(self) -> None:
        """Keep the complete app-derived physical-guide catalogue available."""
        # The app has 229 active entries, but several are usage variants of
        # the same hardware and only 130 unique models expose a local guide.
        self.assertGreaterEqual(len(OFFICIAL_ASSOCIATION_TUTORIALS), 130)

    def test_official_tutorials_contain_no_utf8_latin1_mojibake(self) -> None:
        """All app-derived French instructions must remain readable in HA."""
        corrupted_markers = {"\u00c3", "\u00c2"}
        corrupted_steps = [
            step.text
            for tutorial in OFFICIAL_ASSOCIATION_TUTORIALS.values()
            for step in tutorial
            if any(marker in step.text for marker in corrupted_markers)
        ]

        self.assertEqual(corrupted_steps, [])
        self.assertIn(
            "À l'aide de la télécommande.",
            OFFICIAL_ASSOCIATION_TUTORIALS["TUBAUTO Procom 10-3"][0].text,
        )

    def test_tyxia_5610_uses_its_official_physical_guide(self) -> None:
        """A standard product must expose its own guide, not a generic recipe."""
        tydom_hub = object.__new__(Hub)
        tydom_hub._association_controls = []
        tydom_hub._association_category = "Éclairages"
        tydom_hub._association_product = "TYXIA 5610"
        tydom_hub._association_profile = "official:light_X3D_x3d_rm"
        tydom_hub._association_channel = None

        self.assertEqual(len(tydom_hub.association_instructions), 2)
        self.assertIn("3 secondes", tydom_hub.association_instructions[0])
        self.assertIn("LED rouge", tydom_hub.association_instructions[1])
        self.assertEqual(
            tydom_hub.association_illustration_ids,
            (
                "catalog_7_tyxia_serie4000",
                "catalog_7_tyxia_serie4000_tuto1",
                "catalog_7_tyxia_serie4000_tuto2",
            ),
        )
        self.assertIn(
            "<svg",
            get_association_illustration_svg(
                tydom_hub.association_illustration_ids[0]
            ),
        )
        self.assertIn(
            "Lancer l'écoute de la passerelle",
            tydom_hub.association_instructions[1],
        )

    async def test_association_uses_the_gateway_client(self) -> None:
        """Association is sent through the configured gateway client."""
        client = _Client()
        tydom_hub = SimpleNamespace(_tydom_client=client)

        payload = await start_product_association(tydom_hub, "opening_x3d")

        self.assertEqual(client.payloads, [payload])

    async def test_remote_entry_uses_the_matching_local_gateway(self) -> None:
        """Radio association must not be dispatched through cloud mediation."""
        local_client = _Client()
        local_hub = SimpleNamespace(
            _mac="00:1a:25:04:28:db", _tydom_client=local_client
        )
        remote_hub = SimpleNamespace(
            _mac="001A250428DB",
            _tydom_client=SimpleNamespace(_remote_mode=True),
        )
        remote_hub._hass = SimpleNamespace(
            data={DOMAIN: {"remote-entry": remote_hub, "local-entry": local_hub}}
        )

        payload = await start_product_association(remote_hub, "opening_x3d")

        self.assertEqual(local_client.payloads, [payload])

    async def test_remote_entry_without_local_match_uses_selected_gateway(self) -> None:
        """Cloud-only installations retain the official mediation workflow."""
        remote_client = _Client()
        remote_client._remote_mode = True
        remote_hub = SimpleNamespace(
            _mac="001A250428DB",
            _tydom_client=remote_client,
            _hass=SimpleNamespace(data={DOMAIN: {}}),
        )

        payload = await start_product_association(remote_hub, "opening_x3d")

        self.assertEqual(remote_client.payloads, [payload])

    async def test_removal_rejects_products_without_a_dedicated_group(self) -> None:
        """Potentially shared products must not be removed incompletely."""
        device = SimpleNamespace(_id="42", _tydom_client=SimpleNamespace())

        with self.assertRaisesRegex(ValueError, "not yet available"):
            await remove_product_association(device)

    async def test_interrupter_removal_updates_both_files_before_the_product(
        self,
    ) -> None:
        """A wall-switch removal removes its complete related-endpoints group."""
        calls: list[tuple[str, object]] = []

        config = {
            "endpoints": [
                {"id_device": 42, "id_endpoint": 42},
                {"id_device": 43, "id_endpoint": 43},
            ],
            "groups": [
                {"id": 84, "type": "relatedendpoints"},
                {"id": 85, "type": "group"},
            ],
        }
        groups = {
            "groups": [
                {"id": 84, "devices": [{"id": 42, "endpoints": [{"id": 42}]}]},
                {"id": 85, "devices": [{"id": 43, "endpoints": [{"id": 43}]}]},
            ]
        }

        async def get_config_file_document():
            return config

        async def get_groups_file_document():
            return groups

        async def post_config_file_document(document: dict) -> None:
            calls.append(("config", document))

        async def post_groups_file_document(document: dict) -> None:
            calls.append(("groups", document))

        async def delete_device(device_id: str) -> None:
            calls.append(("device", device_id))

        device = SimpleNamespace(
            _id="42",
            association_group_id="84",
            _tydom_client=SimpleNamespace(
                get_config_file_document=get_config_file_document,
                get_groups_file_document=get_groups_file_document,
                post_config_file_document=post_config_file_document,
                post_groups_file_document=post_groups_file_document,
                delete_device=delete_device,
            ),
        )

        await remove_product_association(device)

        self.assertEqual(
            calls,
            [
                (
                    "config",
                    {
                        "endpoints": [{"id_device": 43, "id_endpoint": 43}],
                        "groups": [{"id": 85, "type": "group"}],
                    },
                ),
                (
                    "groups",
                    {
                        "groups": [
                            {
                                "id": 85,
                                "devices": [{"id": 43, "endpoints": [{"id": 43}]}],
                            }
                        ]
                    },
                ),
                ("device", "42"),
            ],
        )

    async def test_tyxia_2600_migrates_raw_single_button_to_visible_group(self) -> None:
        """A raw one-button discovery becomes one complete groupable product."""
        config = {
            "endpoints": [
                {
                    "id_device": 42,
                    "id_endpoint": 84,
                    "name": "Interrupteur 1",
                    "picto": "picto_interrupter",
                    "first_usage": "interrupter",
                    "last_usage": "interrupter",
                    "anticipation_start": False,
                    "skill": "TYDOM_X3D",
                }
            ],
            "groups": [],
        }
        groups = {"groups": []}
        calls: list[tuple[str, dict]] = []

        async def get_config_file_document() -> dict:
            return config

        async def post_config_file_document(document: dict) -> None:
            calls.append(("config", document))

        async def get_groups_file_document() -> dict:
            return groups

        async def post_groups_file_document(document: dict) -> None:
            calls.append(("groups", document))

        device = SimpleNamespace(
            _id="42",
            _endpoint="84",
            _tydom_client=SimpleNamespace(
                get_config_file_document=get_config_file_document,
                post_config_file_document=post_config_file_document,
                get_groups_file_document=get_groups_file_document,
                post_groups_file_document=post_groups_file_document,
            ),
        )

        with patch(
            "custom_components.deltadore_tydom.hub.secrets.randbelow",
            return_value=11,
        ):
            name = await configure_tyxia_2600_interrupter(device, "Bouton B")

        self.assertEqual(name, "Interrupteur 1")
        self.assertEqual(
            calls,
            [
                (
                    "config",
                    {
                        "endpoints": [
                            {
                                "id_device": 42,
                                "id_endpoint": 84,
                                "name": "CG_DD_COMMON_BUTTONB",
                                "picto": "picto_interrupter",
                                "first_usage": "interrupter",
                                "last_usage": "interrupter",
                                "widget_behavior": {
                                    "tutorial_id": "switch_tyxia2600_btn_b",
                                    "action": "TOGGLE",
                                },
                                "anticipation_start": False,
                                "skill": "TYDOM_X3D",
                            },
                        ],
                        "groups": [
                            {
                                "id": 12,
                                "name": "Interrupteur 1",
                                "picto": "picto_interrupter",
                                "usage": "interrupter",
                                "type": "relatedendpoints",
                                "group_all": False,
                                "is_group_user": False,
                                "widget_behavior": {"tutorial_id": "switch_tyxia2600"},
                            }
                        ],
                    },
                ),
                (
                    "groups",
                    {
                        "groups": [
                            {
                                "id": 12,
                                "devices": [{"id": 42, "endpoints": [{"id": 84}]}],
                                "areas": [],
                            }
                        ]
                    },
                ),
            ],
        )

    async def test_second_tyxia_2600_button_extends_existing_group(self) -> None:
        """A later wired channel extends the existing product rather than duplicating it."""
        config = {
            "endpoints": [
                {
                    "id_device": 42,
                    "id_endpoint": 84,
                    "name": "CG_DD_COMMON_BUTTONA",
                    "picto": "picto_interrupter",
                    "first_usage": "interrupter",
                    "last_usage": "interrupter",
                    "widget_behavior": {
                        "tutorial_id": "switch_tyxia2600_btn_a",
                        "action": "TOGGLE",
                    },
                    "anticipation_start": False,
                    "skill": "TYDOM_X3D",
                }
            ],
            "groups": [
                {
                    "id": 12,
                    "name": "Interrupteur 2",
                    "picto": "picto_interrupter",
                    "usage": "interrupter",
                    "type": "relatedendpoints",
                    "group_all": False,
                    "is_group_user": False,
                    "widget_behavior": {"tutorial_id": "switch_tyxia2600"},
                }
            ],
        }
        groups = {
            "groups": [
                {
                    "id": 12,
                    "devices": [{"id": 42, "endpoints": [{"id": 84}]}],
                    "areas": [],
                }
            ]
        }
        calls: list[tuple[str, dict]] = []

        async def get_config_file_document() -> dict:
            return config

        async def get_groups_file_document() -> dict:
            return groups

        async def post_config_file_document(document: dict) -> None:
            calls.append(("config", document))

        async def post_groups_file_document(document: dict) -> None:
            calls.append(("groups", document))

        device = SimpleNamespace(
            _id="42",
            _endpoint="85",
            _tydom_client=SimpleNamespace(
                get_config_file_document=get_config_file_document,
                get_groups_file_document=get_groups_file_document,
                post_config_file_document=post_config_file_document,
                post_groups_file_document=post_groups_file_document,
            ),
        )

        name = await configure_tyxia_2600_interrupter(device, "Bouton B")

        self.assertEqual(name, "Interrupteur 2")
        self.assertEqual(
            calls,
            [
                (
                    "config",
                    {
                        "endpoints": [
                            {
                                "id_device": 42,
                                "id_endpoint": 84,
                                "name": "CG_DD_COMMON_BUTTONA",
                                "picto": "picto_interrupter",
                                "first_usage": "interrupter",
                                "last_usage": "interrupter",
                                "widget_behavior": {
                                    "action": "TOGGLE",
                                    "tutorial_id": "switch_tyxia2600_btn_a",
                                },
                                "anticipation_start": False,
                                "skill": "TYDOM_X3D",
                            },
                            {
                                "id_device": 42,
                                "id_endpoint": 85,
                                "name": "CG_DD_COMMON_BUTTONB",
                                "picto": "picto_interrupter",
                                "first_usage": "interrupter",
                                "last_usage": "interrupter",
                                "widget_behavior": {
                                    "tutorial_id": "switch_tyxia2600_btn_b",
                                    "action": "TOGGLE",
                                },
                                "anticipation_start": False,
                                "skill": "TYDOM_X3D",
                            },
                        ],
                        "groups": [
                            {
                                "id": 12,
                                "name": "Interrupteur 2",
                                "picto": "picto_interrupter",
                                "usage": "interrupter",
                                "type": "relatedendpoints",
                                "group_all": False,
                                "is_group_user": False,
                                "widget_behavior": {"tutorial_id": "switch_tyxia2600"},
                            }
                        ],
                    },
                ),
                (
                    "groups",
                    {
                        "groups": [
                            {
                                "id": 12,
                                "devices": [
                                    {
                                        "id": 42,
                                        "endpoints": [{"id": 84}, {"id": 85}],
                                    }
                                ],
                                "areas": [],
                            }
                        ]
                    },
                ),
            ],
        )

    async def test_tl2000_uses_the_same_safe_grouping_transaction(self) -> None:
        """A remote-control channel gets an app-visible related-endpoints group."""
        config = {"endpoints": [], "groups": []}
        groups = {"groups": []}
        calls: list[tuple[str, dict]] = []

        async def get_config_file_document() -> dict:
            return config

        async def get_groups_file_document() -> dict:
            return groups

        async def post_config_file_document(document: dict) -> None:
            calls.append(("config", document))

        async def post_groups_file_document(document: dict) -> None:
            calls.append(("groups", document))

        device = SimpleNamespace(
            _id="42",
            _endpoint="84",
            _tydom_client=SimpleNamespace(
                get_config_file_document=get_config_file_document,
                get_groups_file_document=get_groups_file_document,
                post_config_file_document=post_config_file_document,
                post_groups_file_document=post_groups_file_document,
            ),
        )

        with patch(
            "custom_components.deltadore_tydom.hub.secrets.randbelow",
            return_value=11,
        ):
            name = await configure_groupable_product(
                device, GROUPABLE_ASSOCIATION_BY_LABEL["TL 2000"], "Bouton 1"
            )

        self.assertEqual(name, "Télécommande 1")
        endpoint = calls[0][1]["endpoints"][0]
        group = calls[0][1]["groups"][0]
        self.assertEqual(endpoint["name"], "CG_DD_COMMON_BUTTON1")
        self.assertEqual(endpoint["last_usage"], "remoteControl")
        self.assertEqual(endpoint["widget_behavior"]["tutorial_id"], "tl2000_btn_1")
        self.assertEqual(group["name"], "Télécommande 1")
        self.assertEqual(group["usage"], "remoteControl")
        self.assertEqual(group["widget_behavior"]["tutorial_id"], "tl2000")
        self.assertEqual(calls[1][0], "groups")

    async def test_isolated_tyxia_2600_button_removal_updates_config_then_radio(
        self,
    ) -> None:
        """A one-button official app configuration can be removed safely."""
        calls: list[tuple[str, object]] = []
        config = {
            "endpoints": [
                {
                    "id_device": 42,
                    "id_endpoint": 84,
                    "last_usage": "interrupter",
                }
            ],
            "groups": [],
        }
        groups = {"groups": []}

        async def get_config_file_document() -> dict:
            return config

        async def get_groups_file_document() -> dict:
            return groups

        async def post_config_file_document(document: dict) -> None:
            calls.append(("config", document))

        async def delete_device(device_id: str) -> None:
            calls.append(("device", device_id))

        device = TydomInterrupter(
            SimpleNamespace(
                get_config_file_document=get_config_file_document,
                get_groups_file_document=get_groups_file_document,
                post_config_file_document=post_config_file_document,
                delete_device=delete_device,
            ),
            "84_42",
            "42",
            "Button A",
            "interrupter",
            "84",
            None,
            None,
            {"button": "A"},
        )

        await remove_product_association(device)

        self.assertEqual(
            calls, [("config", {"endpoints": [], "groups": []}), ("device", "42")]
        )

    async def test_device_removal_button_is_enabled_and_removes_its_product(
        self,
    ) -> None:
        """The device-page removal control is immediately available."""
        calls: list[str] = []

        async def remove(device) -> None:
            calls.append(device.device_id)

        device = SimpleNamespace(
            device_id="42",
            _id="42",
        )
        button = HADeviceRemovalButton(device, None, remove)

        self.assertTrue(button._attr_entity_registry_enabled_default)

        await button.async_press()

        self.assertEqual(calls, ["42"])

    def test_interrupter_removal_button_is_grouped_with_its_switch(self) -> None:
        """The removal control belongs to the physical wall switch."""
        device = TydomInterrupter(
            MagicMock(),
            "84_42",
            "42",
            "Button A",
            "interrupter",
            "84",
            None,
            None,
            {
                "physical_device_id": "42",
                "name": "Interrupteur 1",
                "model": "TYXIA 2600",
                "button": "A",
            },
        )

        button = HADeviceRemovalButton(device, None)

        self.assertEqual(
            button.device_info["identifiers"], {(DOMAIN, "interrupter_42")}
        )

    def test_twc_scenarios_do_not_receive_product_controls(self) -> None:
        """TWC_UP/DOWN/STOP are virtual scenarios, not removable products."""
        tydom_hub = object.__new__(Hub)
        tydom_hub.add_button_callback = MagicMock()

        tydom_hub._maybe_create_device_association_buttons(object.__new__(TydomScene))

        tydom_hub.add_button_callback.assert_not_called()
