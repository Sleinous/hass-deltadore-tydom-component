"""Ensure absolute thermostat limits have distinct names in every locale."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).parents[1]
TRANSLATIONS = ROOT / "custom_components" / "deltadore_tydom" / "translations"
REFERENCE = "en.json"
DOMAINS = ("sensor", "binary_sensor", "number", "select")
ABSOLUTE_SETPOINTS = {
    "absmaxcoolsetpoint": "maxcoolsetpoint",
    "absmaxheatsetpoint": "maxheatsetpoint",
    "absmincoolsetpoint": "mincoolsetpoint",
    "absminheatsetpoint": "minheatsetpoint",
}


class AbsoluteSetpointNamesTests(TestCase):
    """Keep hardware limits distinct from configured limits."""

    def test_absolute_setpoint_names_are_distinct_in_every_locale(self):
        """Absolute limits must differ from configured setpoints in all locales."""
        english = json.loads((TRANSLATIONS / REFERENCE).read_text(encoding="utf-8"))

        for locale in sorted(TRANSLATIONS.glob("*.json")):
            translated = json.loads(locale.read_text(encoding="utf-8"))
            for domain in DOMAINS:
                names = translated.get("entity", {}).get(domain, {})
                english_names = english.get("entity", {}).get(domain, {})
                for absolute_key, configured_key in ABSOLUTE_SETPOINTS.items():
                    with self.subTest(
                        locale=locale.name,
                        domain=domain,
                        key=absolute_key,
                    ):
                        absolute_name = names.get(absolute_key, {}).get("name")
                        configured_name = names.get(configured_key, {}).get(
                            "name", english_names[configured_key]["name"]
                        )
                        self.assertTrue(absolute_name)
                        self.assertNotEqual(absolute_name, configured_name)
