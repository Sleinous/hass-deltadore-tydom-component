"""Tests for gateway-level TYDOM product association."""

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.deltadore_tydom.hub import (
    ASSOCIATION_CATALOG,
    GROUPABLE_ASSOCIATION_BY_LABEL,
    GROUPABLE_ASSOCIATION_PRODUCTS,
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
    HAGatewayAssociationNameText,
    HADeviceRemovalButton,
)
from custom_components.deltadore_tydom.official_association_tutorials import (
    OFFICIAL_ASSOCIATION_TUTORIALS,
    _COMPLEX_ILLUSTRATION_VECTORS,
    _CURRENT_CATALOGUE_ILLUSTRATION_VECTORS,
    _EXACT_STANDARD_ILLUSTRATION_VECTORS,
    _STANDARD_ILLUSTRATION_VECTORS,
    get_association_illustration_data_url,
    get_association_illustration_layout,
    get_association_illustration_svg,
    get_official_association_tutorial,
    get_official_association_tutorial_id,
)
from custom_components.deltadore_tydom.const import DOMAIN
from custom_components.deltadore_tydom.tydom.tydom_devices import (
    TydomInterrupter,
    TydomRemoteControl,
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

    def test_tyxia_2600_uses_the_remote_discovery_profile(self) -> None:
        """Expose the official TYXIA 2600 profile as an emitter, not a controller."""
        choice = next(
            choice
            for choice in get_association_choices("Interrupteurs")
            if "TYXIA 2600" in choice.label
        )

        self.assertEqual(choice.profile_id, "official:remote_X3D_direct")
        self.assertEqual(
            get_install_payload(choice.profile_id),
            {"protocol": "X3D", "type": "direct", "profile": "remote"},
        )

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

    def test_all_groupable_guides_expose_the_ha_listening_step(self) -> None:
        """Every bespoke remote/switch guide can start association in HA."""
        for product in GROUPABLE_ASSOCIATION_PRODUCTS:
            self.assertTrue(
                any("Lancer l'écoute de la passerelle" in step for step in product.guide),
                product.label,
            )
            self.assertFalse(
                any("Lorsque la confirmation est demandée" in step for step in product.guide),
                product.label,
            )

        tydom_hub = object.__new__(Hub)
        tydom_hub._association_controls = []
        tydom_hub._association_category = "Interrupteurs"
        tydom_hub._association_product = "TYXIA 2600"
        tydom_hub._association_profile = "official:remote_X3D_direct"
        tydom_hub._association_channel = "Bouton A"
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

    def test_groupable_visuals_have_an_explicit_valid_step_mapping(self) -> None:
        """Never infer an illustration's step from its list position."""
        for product in GROUPABLE_ASSOCIATION_PRODUCTS:
            _, illustrations, _ = get_association_illustration_layout(
                product.channels[0].tutorial_id
            )
            self.assertEqual(
                len(product.illustration_step_indexes),
                len(illustrations),
                product.label,
            )
            self.assertTrue(
                all(0 <= index < len(product.guide) for index in product.illustration_step_indexes),
                product.label,
            )

        self.assertEqual(
            GROUPABLE_ASSOCIATION_BY_LABEL["TYXIA 1410"].illustration_step_indexes,
            (1, 2, 3),
        )

    def test_groupable_product_can_keep_an_optional_friendly_name(self) -> None:
        """The name field is limited to groupable products and normalizes text."""
        tydom_hub = object.__new__(Hub)
        tydom_hub._association_controls = []
        tydom_hub._association_category = "Interrupteurs"
        tydom_hub._association_product = "TYXIA 2600"
        tydom_hub._association_profile = "official:remote_X3D_direct"
        tydom_hub._association_name = ""

        tydom_hub.set_association_name("  Entrée   principale ")

        self.assertTrue(tydom_hub.association_name_supported)
        self.assertEqual(tydom_hub.association_name, "Entrée principale")
        self.assertEqual(
            HAGatewayAssociationNameText(tydom_hub).native_value,
            "Entrée principale",
        )

    def test_any_associable_product_exposes_the_optional_name_field(self) -> None:
        """A name may be chosen before any documented association profile."""
        tydom_hub = object.__new__(Hub)
        tydom_hub._association_controls = []
        tydom_hub._association_category = "Éclairages"
        tydom_hub._association_product = "TYXIA 5610"
        tydom_hub._association_profile = "official:light_X3D_x3d_rm"

        self.assertTrue(tydom_hub.association_name_supported)

    def test_new_generic_product_receives_the_requested_ha_name(self) -> None:
        """A generic association applies its requested name after discovery."""
        tydom_hub = object.__new__(Hub)
        tydom_hub._pending_groupable_association = None
        tydom_hub._pending_association_name = "Lampe entrée"
        tydom_hub._pending_association_known_device_ids = {"existing"}
        tydom_hub._hass = MagicMock()
        device = SimpleNamespace(
            device_id="new",
            registry_device_id="new",
            device_name="Produit 2",
        )
        entry = SimpleNamespace(id="entry-id", name="Produit 2")
        registry = MagicMock()
        registry.async_get_device.return_value = entry

        with patch(
            "custom_components.deltadore_tydom.hub.dr.async_get",
            return_value=registry,
        ):
            tydom_hub._maybe_apply_pending_association_name(device)

        registry.async_update_device.assert_called_once_with(
            "entry-id", name="Lampe entrée"
        )
        self.assertIsNone(tydom_hub._pending_association_name)

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

    def test_all_official_vector_colours_are_resolved_for_browsers(self) -> None:
        """Never let an Android @color reference render black in HA."""
        image_ids = set(_COMPLEX_ILLUSTRATION_VECTORS)
        image_ids.update(_CURRENT_CATALOGUE_ILLUSTRATION_VECTORS)
        image_ids.update(_STANDARD_ILLUSTRATION_VECTORS)
        image_ids.update(_EXACT_STANDARD_ILLUSTRATION_VECTORS)

        for image_id in image_ids:
            svg = get_association_illustration_svg(image_id)
            self.assertIsNotNone(svg, image_id)
            self.assertNotIn("@color/", svg, image_id)

        tyxia_5610_step_2 = get_association_illustration_svg(
            "catalog_7_tyxia_serie4000_tuto2"
        )
        self.assertIn('fill="#da483d"', tyxia_5610_step_2)
        transparent_step = get_association_illustration_svg(
            "catalog_rcu_tl2000_btn1_step3"
        )
        self.assertIn('fill-opacity="0.5"', transparent_step)

    def test_current_catalogue_product_uses_its_official_visuals(self) -> None:
        """Newer APK catalogue products must not fall back to a text-only guide."""
        tutorial_id = get_official_association_tutorial_id(
            "SMART PLUG DELTA DORE", "Prise"
        )

        self.assertEqual(tutorial_id, "smart_plug_DD")
        _, steps, stepwise = get_association_illustration_layout(tutorial_id)
        self.assertTrue(stepwise)
        self.assertEqual(steps[0], "catalog_smart_plug_dd_step_check_led")
        self.assertIsNotNone(get_association_illustration_svg(steps[0]))

    def test_current_catalogue_products_keep_their_guides_available(self) -> None:
        """Products with APK visuals must never be shown as guide-less."""
        for product, category in (
            ("SMART PLUG DELTA DORE", "Prise"),
            ("BULB DELTA DORE", "Ã‰clairages"),
            ("NAVILINK PAC", "Thermique"),
            ("THERMOSTAT DELTA 8000", "Thermique"),
        ):
            instructions = get_official_association_tutorial(product, category)
            self.assertTrue(instructions, product)
            self.assertIn("illustr", instructions[0].text, product)

    async def test_unambiguous_tyxia_channel_is_finalized_automatically(self) -> None:
        """A selected TYXIA channel needs no second user action after discovery."""
        tydom_hub = object.__new__(Hub)
        device = SimpleNamespace(device_id="new-tyxia")
        tydom_hub._pending_groupable_association = (MagicMock(), "Bouton A")
        tydom_hub._pending_groupable_candidate_device_id = device.device_id
        tydom_hub._pending_groupable_auto_finalize_failed = False
        tydom_hub._finalize_groupable_product_association = AsyncMock()

        with patch(
            "custom_components.deltadore_tydom.hub.asyncio.sleep", new=AsyncMock()
        ):
            await tydom_hub._async_auto_finalize_groupable_product(device)

        tydom_hub._finalize_groupable_product_association.assert_awaited_once_with(
            device, "Bouton A"
        )

    def test_completed_tyxia_replaces_its_temporary_radio_name(self) -> None:
        """The device page must never retain the discovery-only X3D label."""
        tydom_hub = object.__new__(Hub)
        tydom_hub._hass = MagicMock()
        device = SimpleNamespace(registry_device_id="new-tyxia")
        entry = SimpleNamespace(id="device-registry-id", name="X3D remote control 42")
        registry = MagicMock()
        registry.async_get_device.return_value = entry

        with patch("custom_components.deltadore_tydom.hub.dr.async_get", return_value=registry):
            tydom_hub._rename_new_groupable_device(
                device, "Interrupteur 1", "TYXIA 2600"
            )

        registry.async_update_device.assert_called_once_with(
            "device-registry-id", name="Interrupteur 1", model="TYXIA 2600"
        )

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
        button.hass = SimpleNamespace(bus=bus)

        await button.async_press()

        bus.async_fire.assert_called_once()
        event, payload = bus.async_fire.call_args.args
        self.assertEqual(event, "deltadore_tydom_association_guide")
        self.assertEqual(payload["title"], "TYXIA 2600 — guide d'association (Bouton A)")
        self.assertEqual(payload["instructions"], ["1. Préparez le bouton A."])
        self.assertEqual(len(payload["illustrations"]), 1)
        self.assertTrue(payload["illustrations"][0].startswith("data:image/svg+xml"))
        self.assertEqual(payload["illustration_step_indexes"], [])
        self.assertIsNone(payload["start_association_entity_id"])

    def test_tymoov_radio_exposes_only_each_official_step_visual(self) -> None:
        """Avoid presenting a catalogue thumbnail as an association instruction."""
        overview, steps, stepwise = get_association_illustration_layout("25_tymoov")

        self.assertIsNone(overview)
        self.assertTrue(stepwise)
        self.assertEqual(
            steps,
            ("catalog_25_tymoov_tuto1", "catalog_25_tymoov_tuto2"),
        )

    def test_tyxia_4000_series_retains_its_official_visuals(self) -> None:
        """Keep complete official vectors, including the receiver outline."""
        _, steps, stepwise = get_association_illustration_layout(
            "7_Tyxia_serie4000"
        )

        self.assertTrue(stepwise)
        self.assertEqual(
            steps,
            (
                "catalog_7_tyxia_serie4000_tuto1",
                "catalog_7_tyxia_serie4000_tuto2",
            ),
        )

    def test_overview_only_tutorial_retains_its_official_visual(self) -> None:
        """Do not discard a tutorial's sole official product illustration."""
        overview, steps, stepwise = get_association_illustration_layout("43_tycam_1000")

        self.assertEqual(overview, "catalog_43_tycam_1000")
        self.assertEqual(steps, ())
        self.assertFalse(stepwise)

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

    def test_tysense_sensors_require_a_tywell_bioclimatic_gateway(self) -> None:
        """Do not route RT2012/standard-TYDOM Tysense pairing through HA."""
        tydom_hub = object.__new__(Hub)
        tydom_hub._association_controls = []
        tydom_hub._association_category = "Capteurs"
        tydom_hub._association_product = "Tysense Sun"
        tydom_hub._association_profile = "official:sensor_X3D_direct"
        tydom_hub._id = "gateway"
        tydom_hub.devices = {
            "gateway": SimpleNamespace(
                mainReference="21800010", productName="TYDOM1"
            )
        }

        self.assertNotIn("Tysense Sun", tydom_hub.association_product_labels)
        self.assertNotIn("Tysense Thermo", tydom_hub.association_product_labels)
        self.assertFalse(tydom_hub.association_product_supported)

        tydom_hub.devices["gateway"].productName = "TYDOM PRO"

        self.assertNotIn("Tysense Sun", tydom_hub.association_product_labels)
        self.assertFalse(tydom_hub.association_product_supported)

        tydom_hub.devices["gateway"].productName = "TYWELL HOME"

        self.assertIn("Tysense Sun", tydom_hub.association_product_labels)
        self.assertIn("Tysense Thermo", tydom_hub.association_product_labels)
        self.assertTrue(tydom_hub.association_product_supported)

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

    def test_association_instructions_unescape_catalogue_quotes(self) -> None:
        """Never display JSON escape markers in the Home Assistant guide."""
        tydom_hub = object.__new__(Hub)
        tydom_hub._association_controls = []
        tydom_hub._association_category = "Éclairages"
        tydom_hub._association_product = "TYXIA 4801"
        tydom_hub._association_profile = "official:lighting_X3D_x3d_rm"

        instructions = tydom_hub.association_instructions

        self.assertIn("l'appareil est prêt à être associé.", instructions[1])
        self.assertNotIn("Associer", instructions[1])
        self.assertNotIn('\\"', "\n".join(instructions))

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

    async def test_remote_button_removal_keeps_its_sibling_and_radio_product(
        self,
    ) -> None:
        """Removing one TL 2000/TYXIA 1410 button must retain the remote."""
        calls: list[tuple[str, object]] = []
        config = {
            "endpoints": [
                {"id_device": 42, "id_endpoint": 1, "name": "Button 1"},
                {"id_device": 42, "id_endpoint": 2, "name": "Button 2"},
            ],
            "groups": [{"id": 84, "type": "relatedendpoints"}],
        }
        groups = {
            "groups": [
                {
                    "id": 84,
                    "devices": [
                        {"id": 42, "endpoints": [{"id": 1}, {"id": 2}]}
                    ],
                }
            ]
        }

        async def get_config_file_document() -> dict:
            return config

        async def get_groups_file_document() -> dict:
            return groups

        async def post_config_file_document(document: dict) -> None:
            calls.append(("config", document))

        async def post_groups_file_document(document: dict) -> None:
            calls.append(("groups", document))

        async def delete_device(device_id: str) -> None:
            calls.append(("device", device_id))

        device = TydomRemoteControl(
            SimpleNamespace(
                get_config_file_document=get_config_file_document,
                get_groups_file_document=get_groups_file_document,
                post_config_file_document=post_config_file_document,
                post_groups_file_document=post_groups_file_document,
                delete_device=delete_device,
            ),
            "42_1",
            "42",
            "Button 1",
            "remoteControl",
            "1",
            None,
            None,
            {"physical_device_id": "42", "group_id": "84", "button_number": 1},
        )

        await remove_product_association(device)

        self.assertEqual(
            calls,
            [
                (
                    "config",
                    {
                        "endpoints": [
                            {
                                "id_device": 42,
                                "id_endpoint": 2,
                                "name": "Button 2",
                            }
                        ],
                        "groups": [{"id": 84, "type": "relatedendpoints"}],
                    },
                ),
                (
                    "groups",
                    {
                        "groups": [
                            {
                                "id": 84,
                                "devices": [{"id": 42, "endpoints": [{"id": 2}]}],
                            }
                        ]
                    },
                ),
            ],
        )

        button = HADeviceRemovalButton(device, None)
        self.assertEqual(button._attr_name, "Dissocier le bouton 1")

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

    async def test_groupable_product_uses_the_requested_name_for_new_group(self) -> None:
        """A name entered before pairing becomes the TYDOM group name."""
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
                device,
                GROUPABLE_ASSOCIATION_BY_LABEL["TYXIA 2600"],
                "Bouton A",
                "Entrée",
            )

        self.assertEqual(name, "Entrée")
        self.assertEqual(calls[0][1]["groups"][0]["name"], "Entrée")

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
        self.assertTrue(button.available)

        await button.async_press()

        self.assertEqual(calls, ["42"])

    def test_every_physical_product_gets_an_enabled_removal_button(self) -> None:
        """Removal is a gateway operation, not an endpoint capability."""
        hub = object.__new__(Hub)
        hub._hass = None
        hub.add_button_callback = MagicMock()
        hub._device_association_buttons_created = set()
        hub._pending_groupable_association = None
        hub._association_product = ""
        hub._association_category = ""
        hub._pending_association_name = None
        hub._pending_association_known_device_ids = set()

        # Some products do not advertise ``delete_device`` on their endpoint,
        # but the gateway still owns the radio-level dissociation operation.
        device = SimpleNamespace(
            device_id="1410_42",
            _id="42",
            _metadata={},
            _tydom_client=SimpleNamespace(),
        )

        hub._maybe_create_device_association_buttons(device)

        buttons = hub.add_button_callback.call_args.args[0]
        self.assertEqual(len(buttons), 1)
        self.assertIsInstance(buttons[0], HADeviceRemovalButton)
        self.assertTrue(buttons[0]._attr_entity_registry_enabled_default)

    def test_existing_disabled_removal_button_is_reenabled(self) -> None:
        """A prior disabled registry state must not hide this safety control."""
        hub = object.__new__(Hub)
        hub._hass = object()
        registry = MagicMock()
        registry.async_get_entity_id.return_value = "button.c3_dissociation"
        registry.async_get.return_value = SimpleNamespace(disabled_by="integration")
        button = HADeviceRemovalButton(
            SimpleNamespace(device_id="c3", _id="c3"), None
        )

        with patch(
            "homeassistant.helpers.entity_registry.async_get",
            return_value=registry,
        ):
            hub._enable_existing_removal_buttons([button])

        registry.async_update_entity.assert_called_once_with(
            "button.c3_dissociation", disabled_by=None
        )

    async def test_device_removal_from_its_page_reloads_the_gateway_inventory(
        self,
    ) -> None:
        """A successful device-page removal must not require a manual reload."""
        hub = object.__new__(Hub)
        hub.reload_devices = AsyncMock()
        device = SimpleNamespace(device_id="42")

        with patch(
            "custom_components.deltadore_tydom.hub.remove_product_association",
            new=AsyncMock(),
        ) as remove:
            await hub._remove_product_association_and_reload(device)

        remove.assert_awaited_once_with(device)
        hub.reload_devices.assert_awaited_once_with()

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
