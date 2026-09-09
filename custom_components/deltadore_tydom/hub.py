"""A demonstration 'hub' that connects several devices."""

from __future__ import annotations

import asyncio
import contextlib
import copy
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass

from aiohttp import ClientWebSocketResponse, ClientSession

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .tydom.tydom_client import TydomClient
from .tydom.tydom_devices import (
    Tydom,
    TydomShutter,
    TydomEnergy,
    TydomSmoke,
    TydomBoiler,
    TydomWindow,
    TydomDoor,
    TydomGate,
    TydomGarage,
    TydomLight,
    TydomSwitch,
    TydomInterrupter,
    TydomPlug,
    TydomAlarm,
    TydomWeather,
    TydomWater,
    TydomThermo,
    TydomSun,
    TydomDevice,
    TydomScene,
    TydomGroup,
    TydomMoment,
    TydomRemoteControl,
)
from .ha_entities import (
    HATydom,
    HACover,
    HAEnergy,
    HASmoke,
    HaClimate,
    HaWindow,
    HaDoor,
    HaWindowOpening,
    HaDoorOpening,
    HaGate,
    HaGarage,
    HaLight,
    HAInterrupterBattery,
    HAInterrupterEvent,
    HaAlarm,
    HaWeather,
    HaMoisture,
    HaThermo,
    HaSun,
    HAGenericBinarySensor,
    HASensor,
    HAScene,
    HATwcShutterCover,
    HASwitch,
    HAButton,
    HADeviceAssociationButton,
    HADeviceRemovalButton,
    HATyxia2600FinalizeAssociationButton,
    HAGatewayAssociationCategorySelect,
    HAGatewayAssociationChannelSelect,
    HAGatewayAssociationGuideButton,
    HAGatewayAssociationProductSelect,
    HAGatewayAssociationUsageSelect,
    HAGatewayStartAssociationButton,
    HAAlarmAcknowledgeButton,
    HAAlarmPendingEventsSensor,
    HAReloadButton,
    HARefreshEnergyButton,
    HACoverGroup,
    HALightGroup,
    HASwitchGroup,
    HAMoment,
    HARemoteBattery,
    HARemoteEvent,
    is_binary_attribute,
    ASSOCIATION_COMMAND,
    IDENTIFY_COMMAND,
    supports_command,
)

from .const import DOMAIN, LOGGER, STRUCTURED_LOGGER, get_polling_interval_for_validity
from .remote_registry_migration import migrate_legacy_remote_endpoint


@dataclass(frozen=True, slots=True)
class DiscoveryProfile:
    """One radio/product family accepted by the gateway install API."""

    label: str
    protocol: str
    type: str
    profile: str


@dataclass(frozen=True, slots=True)
class AssociationChoice:
    """A product-family choice shown under one user-facing category."""

    label: str
    profile_id: str | None


# These profiles are the request values used by the official TYDOM app. The
# gateway stays authoritative and accepts only values supported by its firmware.
DISCOVERY_PROFILES: dict[str, DiscoveryProfile] = {
    "alarm_x2d": DiscoveryProfile("TYXAL / alarm X2D", "X3D", "x2d_a", "alarm"),
    "alarm_x3d": DiscoveryProfile("TYXAL+ / alarm X3D", "X3D", "x3d_ppa", "alarm"),
    "aeraulic_zigbee": DiscoveryProfile("Aéraulique Zigbee", "ZIGBEE", "", "aeraulic"),
    "awning_x3d": DiscoveryProfile("Store banne X3D", "X3D", "x3d_rm", "awning"),
    "boiler_drive_x3d": DiscoveryProfile(
        "Chaudière Drive X3D", "X3D", "x3d_rm", "boilerDrive"
    ),
    "controller_x3d": DiscoveryProfile(
        "Contrôleur X3D", "X3D", "x3d_pps", "controller"
    ),
    "detector_x3d": DiscoveryProfile("Détecteur X3D", "X3D", "direct", "detector"),
    "electric_zigbee": DiscoveryProfile(
        "Équipement électrique Zigbee", "ZIGBEE", "", "electric"
    ),
    "light_x3d": DiscoveryProfile("Éclairage X3D", "X3D", "x3d_rm", "light"),
    "light_zigbee": DiscoveryProfile("Éclairage Zigbee", "ZIGBEE", "", "light"),
    "generic_x3d": DiscoveryProfile(
        "Produit générique X3D", "X3D", "x3d_pp", "generic"
    ),
    "meter_x3d": DiscoveryProfile("Compteur / mesure X3D", "X3D", "direct", "meter"),
    "multi_x3d": DiscoveryProfile(
        "Produit multifonction X3D", "X3D", "x3d_pped", "multi"
    ),
    "opening_x3d": DiscoveryProfile(
        "Ouvrant / porte / fenêtre X3D", "X3D", "x3d_rm", "opening"
    ),
    "pod_x3d": DiscoveryProfile("Produit POD X3D", "X3D", "x3d_rm", "pod"),
    "remote_x3d": DiscoveryProfile("Télécommande X3D", "X3D", "direct", "remote"),
    "rt2012_measure_x3d": DiscoveryProfile(
        "Mesure RT2012 X3D", "X3D", "x3d_pped", "rt2012_meas"
    ),
    "rt2012_no_outdoor_temp_x3d": DiscoveryProfile(
        "RT2012 sans sonde extérieure X3D", "X3D", "x3d_pped", "rt2012_noOutTemp"
    ),
    "rt2012_x3d": DiscoveryProfile("RT2012 X3D", "X3D", "x3d_pped", "rt2012"),
    "sensor_x3d": DiscoveryProfile("Capteur X3D", "X3D", "direct", "sensor"),
    "shared_thermic_x3d": DiscoveryProfile(
        "Chauffage partagé X3D", "X3D", "x3d_rmloop", "shThermic"
    ),
    "shutter_x3d": DiscoveryProfile("Volet roulant X3D", "X3D", "x3d_rm", "shutter"),
    "shutter_activhome_x3d": DiscoveryProfile(
        "Volet Activ'Home X3D", "X3D", "x3d_rm", "shutterActivHome"
    ),
    "shutter_brushless_x3d": DiscoveryProfile(
        "Volet Brushless X3D", "X3D", "x3d_rm", "shutterBrushless"
    ),
    "shutter_projected_x3d": DiscoveryProfile(
        "Volet projeté X3D", "X3D", "x3d_rm", "shutterProjected"
    ),
    "shutter_profalux_zigbee": DiscoveryProfile(
        "Volet Profalux Zigbee", "ZIGBEE", "PROFALUX", "shutter"
    ),
    "shutter_rmlp_x3d": DiscoveryProfile(
        "Volet RMLP X3D", "X3D", "x3d_rmlp", "shutter"
    ),
    "shutter_stella_zigbee": DiscoveryProfile(
        "Volet Stella Zigbee", "ZIGBEE", "", "shutter"
    ),
    "shutter_zigbee": DiscoveryProfile("Volet roulant Zigbee", "ZIGBEE", "", "shutter"),
    "temperature_x3d": DiscoveryProfile(
        "Sonde de température X3D", "X3D", "direct", "temperature"
    ),
    "thermic_x3d": DiscoveryProfile("Chauffage X3D", "X3D", "x3d_rm", "thermic"),
    "thermic_x2d": DiscoveryProfile("Chauffage X2D", "X3D", "x2d_d", "thermic"),
    "thermic_x3d_es": DiscoveryProfile(
        "Chauffage X3D (émetteur spécifique)", "X3D", "x3d_rm", "thermicES"
    ),
    "thermic_zigbee": DiscoveryProfile("Chauffage Zigbee", "ZIGBEE", "", "thermic"),
    "typass_atl_x3d": DiscoveryProfile("TYPASS ATL X3D", "X3D", "direct", "typassAtl"),
    "typass_saunier_x3d": DiscoveryProfile(
        "TYPASS Saunier X3D", "X3D", "direct", "typassSaunier"
    ),
    "weather_plt": DiscoveryProfile("Station météo", "PltService", "", "weather"),
}


# The official application first asks for a usage, then a product family. Keep
# its initial list of groups intact. A recipe may occur in several categories.
ASSOCIATION_CATALOG: dict[str, tuple[AssociationChoice, ...]] = {
    "Volets": (
        AssociationChoice("Récepteur volet roulant X3D", "shutter_x3d"),
        AssociationChoice("Volet Activ'Home", "shutter_activhome_x3d"),
        AssociationChoice("Volet Brushless", "shutter_brushless_x3d"),
        AssociationChoice("Volet projeté", "shutter_projected_x3d"),
        AssociationChoice("Volet Profalux Zigbee", "shutter_profalux_zigbee"),
        AssociationChoice("Volet Stella Zigbee", "shutter_stella_zigbee"),
        AssociationChoice("Volet roulant Zigbee", "shutter_zigbee"),
    ),
    "Éclairages": (
        AssociationChoice("Récepteur éclairage X3D", "light_x3d"),
        AssociationChoice("Éclairage Zigbee", "light_zigbee"),
    ),
    "Thermique": (
        AssociationChoice("Récepteur chauffage X3D", "thermic_x3d"),
        AssociationChoice("Récepteur chauffage X2D", "thermic_x2d"),
        AssociationChoice("Émetteur chauffage X3D spécifique", "thermic_x3d_es"),
        AssociationChoice("Chaudière Drive", "boiler_drive_x3d"),
        AssociationChoice("Chauffage Zigbee", "thermic_zigbee"),
        AssociationChoice("Chauffage partagé X3D", "shared_thermic_x3d"),
        AssociationChoice("TYPASS ATL", "typass_atl_x3d"),
        AssociationChoice("TYPASS Saunier", "typass_saunier_x3d"),
        AssociationChoice("Aéraulique Zigbee", "aeraulic_zigbee"),
    ),
    "Garage": (
        AssociationChoice("Récepteur portail / garage X3D", "light_x3d"),
        AssociationChoice("Récepteur volet / garage X3D", "shutter_x3d"),
        AssociationChoice("Volet Profalux Zigbee", "shutter_profalux_zigbee"),
    ),
    "Portail": (
        AssociationChoice("Récepteur portail X3D", "light_x3d"),
        AssociationChoice("Produit générique X3D", "generic_x3d"),
    ),
    "Alarme": (
        AssociationChoice("TYXAL / alarme X2D", "alarm_x2d"),
        AssociationChoice("TYXAL+ / alarme X3D", "alarm_x3d"),
        AssociationChoice("Détecteur X3D", "detector_x3d"),
        AssociationChoice("Télécommande / clavier X3D", "remote_x3d"),
    ),
    "Caméras": (AssociationChoice("Aucun profil local documenté", None),),
    "Consommation": (
        AssociationChoice("Compteur ou mesure X3D", "meter_x3d"),
        AssociationChoice("RT2012", "rt2012_x3d"),
        AssociationChoice("RT2012 sans sonde extérieure", "rt2012_no_outdoor_temp_x3d"),
        AssociationChoice("Mesure RT2012", "rt2012_measure_x3d"),
    ),
    "Porte": (
        AssociationChoice("Ouvrant, porte ou fenêtre X3D", "opening_x3d"),
        AssociationChoice("Produit POD X3D", "pod_x3d"),
    ),
    "Fenêtres": (
        AssociationChoice("Ouvrant, porte ou fenêtre X3D", "opening_x3d"),
        AssociationChoice("Produit POD X3D", "pod_x3d"),
    ),
    "Stores": (
        AssociationChoice("Store banne X3D", "awning_x3d"),
        AssociationChoice("Store projeté X3D", "shutter_projected_x3d"),
    ),
    "Prise": (
        AssociationChoice("Prise / équipement électrique Zigbee", "electric_zigbee"),
        AssociationChoice("Récepteur prise X3D", "light_x3d"),
    ),
    "Autres": (
        AssociationChoice("Produit générique X3D", "generic_x3d"),
        AssociationChoice("Produit multifonction X3D", "multi_x3d"),
        AssociationChoice("Produit POD X3D", "pod_x3d"),
        AssociationChoice("Station météo", "weather_plt"),
    ),
    "Télécommandes et claviers": (
        AssociationChoice("Télécommande / émetteur X3D (ex. TYXIA 2600)", "remote_x3d"),
        AssociationChoice("Contrôleur X3D", "controller_x3d"),
    ),
    "Interrupteurs": (
        AssociationChoice("Interrupteur / récepteur éclairage X3D", "light_x3d"),
        AssociationChoice("Éclairage Zigbee", "light_zigbee"),
        AssociationChoice("Interrupteur / émetteur X3D (ex. TYXIA 2600)", "remote_x3d"),
        AssociationChoice("Contrôleur X3D", "controller_x3d"),
    ),
    "Capteurs": (
        AssociationChoice("Capteur X3D", "sensor_x3d"),
        AssociationChoice("Détecteur X3D", "detector_x3d"),
        AssociationChoice("Sonde de température X3D", "temperature_x3d"),
        AssociationChoice("Station météo", "weather_plt"),
    ),
}

# Official product-to-discovery mappings are kept separately from the
# generic fallback recipes above. They are generated from the product catalog
# bundled with the official TYDOM application, but only the small, declarative
# association facts are versioned here (never the APK itself).
OFFICIAL_DISCOVERY_PROFILES: dict[str, DiscoveryProfile] = {
    "official:aeraulic_ZIGBEE": DiscoveryProfile(
        "aeraulic_ZIGBEE", "ZIGBEE", "", "aeraulic"
    ),
    "official:alarm_X3D_x2d_a": DiscoveryProfile(
        "alarm_X3D_x2d_a", "X3D", "x2d_a", "alarm"
    ),
    "official:alarm_X3D_x3d_ppa": DiscoveryProfile(
        "alarm_X3D_x3d_ppa", "X3D", "x3d_ppa", "alarm"
    ),
    "official:awning_X3D_x3d_rm": DiscoveryProfile(
        "awning_X3D_x3d_rm", "X3D", "x3d_rm", "awning"
    ),
    "official:detector_X3D_direct": DiscoveryProfile(
        "detector_X3D_direct", "X3D", "direct", "detector"
    ),
    "official:electric_ZIGBEE": DiscoveryProfile(
        "electric_ZIGBEE", "ZIGBEE", "", "electric"
    ),
    "official:generic_X3D_x3d_pp": DiscoveryProfile(
        "generic_X3D_x3d_pp", "X3D", "x3d_pp", "generic"
    ),
    "official:light_X3D_x3d_rm": DiscoveryProfile(
        "light_X3D_x3d_rm", "X3D", "x3d_rm", "light"
    ),
    "official:light_ZIGBEE": DiscoveryProfile("light_ZIGBEE", "ZIGBEE", "", "light"),
    "official:meter_X3D_direct": DiscoveryProfile(
        "meter_X3D_direct", "X3D", "direct", "meter"
    ),
    "official:multi_X3D_x3d_pped": DiscoveryProfile(
        "multi_X3D_x3d_pped", "X3D", "x3d_pped", "multi"
    ),
    "official:opening_x3d_x3d_rm": DiscoveryProfile(
        "opening_x3d_x3d_rm", "X3D", "x3d_rm", "opening"
    ),
    "official:pod_X3D_x3d_rm": DiscoveryProfile(
        "pod_X3D_x3d_rm", "X3D", "x3d_rm", "pod"
    ),
    "official:remote_X3D_direct": DiscoveryProfile(
        "remote_X3D_direct", "X3D", "direct", "remote"
    ),
    "official:rt2012_meas_X3D_x3d_pped": DiscoveryProfile(
        "rt2012_meas_X3D_x3d_pped", "X3D", "x3d_pped", "rt2012_meas"
    ),
    "official:rt2012_noOutTemp_X3D_x3d_pped": DiscoveryProfile(
        "rt2012_noOutTemp_X3D_x3d_pped", "X3D", "x3d_pped", "rt2012_noOutTemp"
    ),
    "official:rt2012_X3D_x3d_pped": DiscoveryProfile(
        "rt2012_X3D_x3d_pped", "X3D", "x3d_pped", "rt2012"
    ),
    "official:sensor_X3D_direct": DiscoveryProfile(
        "sensor_X3D_direct", "X3D", "direct", "sensor"
    ),
    "official:shThermic_X3D_x3d_rmloop": DiscoveryProfile(
        "shThermic_X3D_x3d_rmloop", "X3D", "x3d_rmloop", "shThermic"
    ),
    "official:shutter_X3D_x3d_rm": DiscoveryProfile(
        "shutter_X3D_x3d_rm", "X3D", "x3d_rm", "shutter"
    ),
    "official:shutter_X3D_x3d_rmlp": DiscoveryProfile(
        "shutter_X3D_x3d_rmlp", "X3D", "x3d_rmlp", "shutter"
    ),
    "official:shutter_ZIGBEE": DiscoveryProfile(
        "shutter_ZIGBEE", "ZIGBEE", "", "shutter"
    ),
    "official:shutter_ZIGBEE_PROFALUX": DiscoveryProfile(
        "shutter_ZIGBEE_PROFALUX", "ZIGBEE", "PROFALUX", "shutter"
    ),
    "official:shutter_ZIGBEE_STELLA": DiscoveryProfile(
        "shutter_ZIGBEE_STELLA", "ZIGBEE", "", "shutter"
    ),
    "official:shutterActivHome_X3D_x3d_rm": DiscoveryProfile(
        "shutterActivHome_X3D_x3d_rm", "X3D", "x3d_rm", "shutterActivHome"
    ),
    "official:shutterBrushless_X3D_x3d_rm": DiscoveryProfile(
        "shutterBrushless_X3D_x3d_rm", "X3D", "x3d_rm", "shutterBrushless"
    ),
    "official:shutterProjected_X3D_x3d_rm": DiscoveryProfile(
        "shutterProjected_X3D_x3d_rm", "X3D", "x3d_rm", "shutterProjected"
    ),
    "official:temperature_X3D_direct": DiscoveryProfile(
        "temperature_X3D_direct", "X3D", "direct", "temperature"
    ),
    "official:thermic_X3D_x2d_d": DiscoveryProfile(
        "thermic_X3D_x2d_d", "X3D", "x2d_d", "thermic"
    ),
    "official:thermic_X3D_x3d_pps": DiscoveryProfile(
        "thermic_X3D_x3d_pps", "X3D", "x3d_pps", "controller"
    ),
    "official:thermic_X3D_x3d_rm": DiscoveryProfile(
        "thermic_X3D_x3d_rm", "X3D", "x3d_rm", "thermic"
    ),
    "official:thermic_X3D_x3d_rm_drive": DiscoveryProfile(
        "thermic_X3D_x3d_rm_drive", "X3D", "x3d_rm", "boilerDrive"
    ),
    "official:thermic_X3D_x3d_rm_es": DiscoveryProfile(
        "thermic_X3D_x3d_rm_es", "X3D", "x3d_rm", "thermicES"
    ),
    "official:thermic_ZIGBEE": DiscoveryProfile(
        "thermic_ZIGBEE", "ZIGBEE", "", "thermic"
    ),
    "official:typassATL_X3D_direct": DiscoveryProfile(
        "typassATL_X3D_direct", "X3D", "direct", "typassAtl"
    ),
    "official:typassSaunier_X3D_direct": DiscoveryProfile(
        "typassSaunier_X3D_direct", "X3D", "direct", "typassSaunier"
    ),
    "official:weather_plt": DiscoveryProfile(
        "weather_plt", "PltService", "", "weather"
    ),
}


# The TYXIA 2600 is not a generic radio product: its two physical buttons are
# associated independently. The documented "remote control" process starts
# with button A, irrespective of the selected channel, then confirms that
# selected channel only after the gateway has entered association mode.
TYXIA_2600_ASSOCIATION_CHANNELS = ("Bouton A", "Bouton B")
TYXIA_2600_ASSOCIATION_GUIDE = (
    "Parcours Home Assistant — ajout du TYXIA 2600 comme télécommande :",
    "1. Dans Home Assistant, choisissez d'abord la voie à associer : {channel}.",
    "2. Maintenez le bouton A physique pendant 6 secondes. Le voyant rouge "
    "s'allume, s'éteint, puis reste fixe : relâchez alors le bouton.",
    "3. Le voyant vert clignote par séries. Appuyez sur A pour faire défiler "
    "les modes, puis conservez le mode correspondant à l'association voulue.",
    "4. Maintenez B pendant 3 secondes, jusqu'à l'allumage du voyant vert, "
    "pour valider le mode sélectionné.",
    "5. Dans Home Assistant, appuyez sur « Lancer l'écoute de la passerelle » "
    "avant de poursuivre avec le TYXIA 2600.",
    "6. Maintenez le bouton A physique pendant 3 secondes, jusqu'à ce que le "
    "voyant rouge clignote.",
    "7. Attendez pendant que l'association est en cours.",
    "8. Lorsque la confirmation est demandée, appuyez sur le bouton de "
    "l'interrupteur relié à la voie {button} ({channel}).",
)

OFFICIAL_ASSOCIATION_CATALOG: dict[str, tuple[AssociationChoice, ...]] = {
    "Volets": (
        AssociationChoice("ACTIVE HOME KLINE", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("BRISE SOLEIL WELLCOM", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("BRISE SOLEIL ZIGBEE", "official:shutter_ZIGBEE_PROFALUX"),
        AssociationChoice("BSO KLINE", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("KLINE TYMOOV SOLAR", "official:shutter_X3D_x3d_rmlp"),
        AssociationChoice("PROFALUX BRANDS", "official:shutter_ZIGBEE_PROFALUX"),
        AssociationChoice("PROFALUX STELLA SHUTTER", "official:shutter_ZIGBEE_STELLA"),
        AssociationChoice("ROLLIA RADIO", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("SHUTTER TYMOOV SOLAR", "official:shutter_X3D_x3d_rmlp"),
        AssociationChoice("STORE VERTICAL ZIGBEE", "official:shutter_ZIGBEE_PROFALUX"),
        AssociationChoice("TYMOOV RADIO", "official:shutterBrushless_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4630", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4730", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4731", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("TYXIA 5630", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("TYXIA 5730", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("TYXIA 5731", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("VLO BUBENDORFF SHUTTER", "official:shutter_ZIGBEE"),
        AssociationChoice("VOLET BATTANT WELLCOM", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("VOLET KLINE", "official:shutter_X3D_x3d_rm"),
        AssociationChoice(
            "VOLET PROJECTION WELLCOM", "official:shutterProjected_X3D_x3d_rm"
        ),
        AssociationChoice("VOLET ROULANT WELLCOM", "official:shutter_X3D_x3d_rm"),
        AssociationChoice(
            "VOLET ROULANT WELLCOM SOLAR", "official:shutter_X3D_x3d_rmlp"
        ),
        AssociationChoice("VOLET ROULANT ZIGBEE", "official:shutter_ZIGBEE_PROFALUX"),
        AssociationChoice("VR BUBENDORFF SHUTTER", "official:shutter_ZIGBEE"),
    ),
    "Éclairages": (
        AssociationChoice("BULB DELTA DORE", "official:light_ZIGBEE"),
        AssociationChoice("BULB GENERIQUE", "official:light_ZIGBEE"),
        AssociationChoice("TYXIA 4600", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4610", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4801", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4811", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4840", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4850", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4860", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4910", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4940", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 5610", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 5612", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 5640", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 5650", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 6410", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 6610", "official:light_X3D_x3d_rm"),
    ),
    "Thermique": (
        AssociationChoice("ALLAUVE KONECT", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("ATLANTIC", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("CALYBOX 1020 WT", "official:rt2012_noOutTemp_X3D_x3d_pped"),
        AssociationChoice("CALYBOX 2020 WT", "official:rt2012_X3D_x3d_pped"),
        AssociationChoice("CALYBOX 210", "official:thermic_X3D_x2d_d"),
        AssociationChoice("CALYBOX 220", "official:thermic_X3D_x2d_d"),
        AssociationChoice("CALYBOX 220 WT", "official:thermic_X3D_x2d_d"),
        AssociationChoice("CALYBOX 230", "official:thermic_X3D_x2d_d"),
        AssociationChoice("CALYBOX 230 WT", "official:thermic_X3D_x2d_d"),
        AssociationChoice("CALYBOX 320", "official:thermic_X3D_x2d_d"),
        AssociationChoice("CALYBOX 320 WT", "official:thermic_X3D_x2d_d"),
        AssociationChoice("CALYBOX 330", "official:thermic_X3D_x2d_d"),
        AssociationChoice("CALYBOX 420", "official:thermic_X3D_x2d_d"),
        AssociationChoice("CALYBOX 430", "official:thermic_X3D_x2d_d"),
        AssociationChoice("DELTA 8000", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("HITACHI ATW", "official:thermic_X3D_x3d_rm_es"),
        AssociationChoice("HOMEPILOTE PURE", "official:thermic_X3D_x3d_rm_es"),
        AssociationChoice("MINOR 1000", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("MULTIZONE KIT", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("NAVILINK PAC", "official:thermic_ZIGBEE"),
        AssociationChoice("NAVILINK PAC BOILER", "official:thermic_ZIGBEE"),
        AssociationChoice("NSC RF ELM Leblanc", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("PARTNER HVAC", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("RADIO TYBOX 810 (RF 640)", "official:thermic_X3D_x2d_d"),
        AssociationChoice("RADIO TYBOX 811 (RF 640)", "official:thermic_X3D_x2d_d"),
        AssociationChoice("RF 4890", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("RF 6050+", "official:thermic_X3D_x3d_rm_es"),
        AssociationChoice("RF 6600 FP", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("RF 6620", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("RF 6630", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("RF 6640", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("RF 6650", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("RF 6700 FP", "official:thermic_X3D_x3d_rm_es"),
        AssociationChoice("RF 7110", "official:thermic_X3D_x3d_rm_es"),
        AssociationChoice("RF 7130", "official:thermic_X3D_x3d_rm_es"),
        AssociationChoice("RF 7210", "official:thermic_X3D_x3d_rm_es"),
        AssociationChoice("SPLIT TAKAO", "official:aeraulic_ZIGBEE"),
        AssociationChoice("TA 5555 ZIGBEE DD", "official:electric_ZIGBEE"),
        AssociationChoice("TA 5555 ZIGBEE OTHERS", "official:electric_ZIGBEE"),
        AssociationChoice("THERMOSTAT ATLANTIC", "official:temperature_X3D_direct"),
        AssociationChoice("THERMOSTAT DELTA 8000", "official:temperature_X3D_direct"),
        AssociationChoice(
            "THERMOSTAT MULTIZONE KIT", "official:temperature_X3D_direct"
        ),
        AssociationChoice("TRV 1.0", "official:shThermic_X3D_x3d_rmloop"),
        AssociationChoice("TRV 2", "official:thermic_ZIGBEE"),
        AssociationChoice("TYBOX 1010 WT", "official:rt2012_noOutTemp_X3D_x3d_pped"),
        AssociationChoice("TYBOX 1137 (RF6000+)", "official:thermic_X3D_x3d_rm_es"),
        AssociationChoice("TYBOX 137 (RF 640)", "official:thermic_X3D_x2d_d"),
        AssociationChoice("TYBOX 137+ (RF6000+)", "official:thermic_X3D_x3d_rm_es"),
        AssociationChoice("TYBOX 2010 WT", "official:rt2012_X3D_x3d_pped"),
        AssociationChoice("TYBOX 2300 (RF 6000+)", "official:thermic_X3D_x3d_rm_es"),
        AssociationChoice("TYBOX 237 (RF 640)", "official:thermic_X3D_x2d_d"),
        AssociationChoice("TYBOX 337 (RF 640)", "official:thermic_X3D_x2d_d"),
        AssociationChoice("TYBOX 4100", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("TYBOX 4110", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("TYBOX 4150", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("TYBOX 4210", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("TYBOX 4250", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("TYBOX 5000", "official:multi_X3D_x3d_pped"),
        AssociationChoice("TYBOX 5100 (RF 6000)", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("TYBOX 5150 (RF 6200)", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("TYBOX 5200 (RF 6050)", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("TYBOX 5300 (RF 6050+)", "official:thermic_X3D_x3d_rm_es"),
        AssociationChoice(
            "TYBOX 5701 FP (RF 6700 FP)", "official:thermic_X3D_x3d_rm_es"
        ),
        AssociationChoice(
            "TYBOX 5702 FP (2 x RF 6700 FP)", "official:thermic_X3D_x3d_rm_es"
        ),
        AssociationChoice(
            "TYBOX HOME RF 210 (RF 7210)", "official:thermic_X3D_x3d_rm_es"
        ),
        AssociationChoice("TYBOX RF 110 (RF 7110)", "official:thermic_X3D_x3d_rm_es"),
        AssociationChoice("TYBOX RF 130 (RF 7130)", "official:thermic_X3D_x3d_rm_es"),
        AssociationChoice("TYBOX RF 210 (RF 7210)", "official:thermic_X3D_x3d_rm_es"),
        AssociationChoice(
            "TYBOX RF 210 XL (RF 7210)", "official:thermic_X3D_x3d_rm_es"
        ),
        AssociationChoice("TYPASS ATL", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("TYPASS CHX", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("TYPASS SD", "official:thermic_X3D_x3d_rm"),
        AssociationChoice("Tywell 2050 (RF 6050+)", "official:thermic_X3D_x3d_rm_es"),
        AssociationChoice("Tywell 2050 L (RF 6050+)", "official:thermic_X3D_x3d_rm_es"),
    ),
    "Garage": (
        AssociationChoice("GARAGE HORIZONTAL WELLCOM", "official:light_X3D_x3d_rm"),
        AssociationChoice("GARAGE VERTICAL WELLCOM", "official:light_X3D_x3d_rm"),
        AssociationChoice("HORMANN SupraMatic", "official:light_X3D_x3d_rm"),
        AssociationChoice("NOVOFERM Novomatic 423", "official:light_X3D_x3d_rm"),
        AssociationChoice("NOVOFERM Novomatic 563", "official:light_X3D_x3d_rm"),
        AssociationChoice("NOVOFERM Novoport", "official:light_X3D_x3d_rm"),
        AssociationChoice("ROLLIA RADIO", "official:shutter_X3D_x3d_rm"),
        AssociationChoice(
            "SOMMER ROLLER DOOR CONTROL UNIT", "official:light_X3D_x3d_rm"
        ),
        AssociationChoice("SOMMER S 90XX HORIZONTAL", "official:light_X3D_x3d_rm"),
        AssociationChoice("SOMMER S 90XX VERTICAL", "official:light_X3D_x3d_rm"),
        AssociationChoice("TUBAUTO Procom 10-3", "official:light_X3D_x3d_rm"),
        AssociationChoice("TUBAUTO Procom 10-4", "official:light_X3D_x3d_rm"),
        AssociationChoice("TUBAUTO Procom 20-3", "official:light_X3D_x3d_rm"),
        AssociationChoice("TUBAUTO Procom 20-4", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYMOOV RADIO", "official:shutterBrushless_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4620", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4630", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4730", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("TYXIA 5630", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("TYXIA 5730", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("TYXIA 6410", "official:light_X3D_x3d_rm"),
        AssociationChoice(
            "WELLCOM ROLLER DOOR CONTROL UNIT", "official:light_X3D_x3d_rm"
        ),
        AssociationChoice("WELLCOM S 90XX HORIZONTAL", "official:light_X3D_x3d_rm"),
        AssociationChoice("WELLCOM S 90XX VERTICAL", "official:light_X3D_x3d_rm"),
    ),
    "Portail": (
        AssociationChoice("SOMMER STARTER S 2 COULISSANT", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4620", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 6410", "official:light_X3D_x3d_rm"),
    ),
    "Alarme": (
        AssociationChoice("CSTX 50", "official:alarm_X3D_x2d_a"),
        AssociationChoice("CSX 20", "official:alarm_X3D_x2d_a"),
        AssociationChoice("CSX 40", "official:alarm_X3D_x2d_a"),
        AssociationChoice("CTX 60", "official:alarm_X3D_x2d_a"),
        AssociationChoice("DELTAL 2.00", "official:alarm_X3D_x2d_a"),
        AssociationChoice("DELTAL 2.10", "official:alarm_X3D_x2d_a"),
        AssociationChoice("DELTAL 2.15", "official:alarm_X3D_x2d_a"),
        AssociationChoice("DELTAL 2.50", "official:alarm_X3D_x2d_a"),
        AssociationChoice("DELTAL 3.00", "official:alarm_X3D_x2d_a"),
        AssociationChoice("DELTAL 4.00", "official:alarm_X3D_x2d_a"),
        AssociationChoice("DELTAL 4.50", "official:alarm_X3D_x2d_a"),
        AssociationChoice("DELTAL 7.00", "official:alarm_X3D_x2d_a"),
        AssociationChoice("EVOLOGY 2 ZONES", "official:alarm_X3D_x2d_a"),
        AssociationChoice("EVOLOGY 4 ZONES", "official:alarm_X3D_x2d_a"),
        AssociationChoice("HUB ALARM", "official:alarm_X3D_x3d_ppa"),
        AssociationChoice("KIT EVOLUTYX 26", "official:alarm_X3D_x2d_a"),
        AssociationChoice("KIT HABITAT 10", "official:alarm_X3D_x2d_a"),
        AssociationChoice("KIT HABITAT 20", "official:alarm_X3D_x2d_a"),
        AssociationChoice("KIT TYXAL 20", "official:alarm_X3D_x2d_a"),
        AssociationChoice("KIT TYXAL 30", "official:alarm_X3D_x2d_a"),
        AssociationChoice("KIT TYXAL 5", "official:alarm_X3D_x2d_a"),
        AssociationChoice("KIT TYXAL 50", "official:alarm_X3D_x2d_a"),
        AssociationChoice("KIT TYXAL 51", "official:alarm_X3D_x2d_a"),
        AssociationChoice("KIT TYXAL 70", "official:alarm_X3D_x2d_a"),
        AssociationChoice("KIT TYXAL 71", "official:alarm_X3D_x2d_a"),
        AssociationChoice("PACK TYXAL APPARTEMENT", "official:alarm_X3D_x2d_a"),
        AssociationChoice("PACK TYXAL MAISON", "official:alarm_X3D_x2d_a"),
        AssociationChoice("PACK TYXAL MAISON ANIMAUX", "official:alarm_X3D_x2d_a"),
        AssociationChoice("TYXAL PLUS PACK CS 8000", "official:alarm_X3D_x3d_ppa"),
        AssociationChoice("TYXAL PLUS VIRGIN", "official:alarm_X3D_x3d_ppa"),
        AssociationChoice("TYXAL PLUS WITH CLT 8000", "official:alarm_X3D_x3d_ppa"),
        AssociationChoice("TYXAL PLUS WITH TL 2000", "official:alarm_X3D_x3d_ppa"),
    ),
    "Consommation": (
        AssociationChoice("CALYBOX 1020 WT", "official:rt2012_noOutTemp_X3D_x3d_pped"),
        AssociationChoice("CALYBOX 2020 WT", "official:rt2012_X3D_x3d_pped"),
        AssociationChoice("EM.IC", "official:generic_X3D_x3d_pp"),
        AssociationChoice("HITACHI ATW", "official:typassATL_X3D_direct"),
        AssociationChoice("TYBOX 1010 WT", "official:rt2012_noOutTemp_X3D_x3d_pped"),
        AssociationChoice("TYBOX 2000 WT", "official:rt2012_X3D_x3d_pped"),
        AssociationChoice("TYBOX 2010 WT", "official:rt2012_X3D_x3d_pped"),
        AssociationChoice("TYBOX 2020 WT", "official:rt2012_X3D_x3d_pped"),
        AssociationChoice("TYPASS ATL", "official:typassATL_X3D_direct"),
        AssociationChoice("TYPASS CHX", "official:typassATL_X3D_direct"),
        AssociationChoice("TYPASS SD", "official:typassSaunier_X3D_direct"),
        AssociationChoice("Tysense Thermo", "official:temperature_X3D_direct"),
        AssociationChoice("TYWATT 1000", "official:rt2012_noOutTemp_X3D_x3d_pped"),
        AssociationChoice("TYWATT 2000", "official:rt2012_X3D_x3d_pped"),
        AssociationChoice("TYWATT 5100", "official:meter_X3D_direct"),
        AssociationChoice("TYWATT 5400", "official:generic_X3D_x3d_pp"),
        AssociationChoice("TYWATT 5450", "official:generic_X3D_x3d_pp"),
        AssociationChoice("TYWATT 5600", "official:generic_X3D_x3d_pp"),
    ),
    "Porte": (
        AssociationChoice("CAPTEUR CPA", "official:detector_X3D_direct"),
        AssociationChoice("DETECTEUR OUVERTURE", "official:detector_X3D_direct"),
        AssociationChoice("DETECTEUR VERROUILLAGE DVI", "official:detector_X3D_direct"),
        AssociationChoice("I-SECURE (CPA)", "official:detector_X3D_direct"),
        AssociationChoice("POD", "official:pod_X3D_x3d_rm"),
        AssociationChoice("PORTE BELEM", "official:pod_X3D_x3d_rm"),
    ),
    "Fenêtres": (
        AssociationChoice("CAPTEUR CPA", "official:detector_X3D_direct"),
        AssociationChoice("DETECTEUR OUVERTURE", "official:detector_X3D_direct"),
        AssociationChoice(
            "DETECTEUR VERROUILLAGE DVI SLIDING", "official:detector_X3D_direct"
        ),
        AssociationChoice(
            "DETECTEUR VERROUILLAGE DVI SWING", "official:detector_X3D_direct"
        ),
        AssociationChoice("I-SECURE (CPA)", "official:detector_X3D_direct"),
        AssociationChoice("USAGE DETECT WINDOW FPI", "official:opening_x3d_x3d_rm"),
    ),
    "Stores": (
        AssociationChoice("PROFALUX STELLA STORE", "official:shutter_ZIGBEE_STELLA"),
        AssociationChoice("ROLLIA RADIO", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("STORE WELLCOM", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("TYMOOV RADIO", "official:shutterBrushless_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4630", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4730", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4731", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("TYXIA 5630", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("TYXIA 5730", "official:shutter_X3D_x3d_rm"),
        AssociationChoice("TYXIA 5731", "official:shutter_X3D_x3d_rm"),
    ),
    "Prise": (
        AssociationChoice("SMART PLUG DELTA DORE", "official:light_ZIGBEE"),
        AssociationChoice("SMART PLUG GENERIQUE", "official:light_ZIGBEE"),
    ),
    "Autres": (
        AssociationChoice("TYXIA 4600", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4610", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4620", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4801", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4811", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4840", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4850", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4860", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4910", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 4940", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 5610", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 5612", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 5640", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 5650", "official:light_X3D_x3d_rm"),
        AssociationChoice("TYXIA 6410", "official:light_X3D_x3d_rm"),
    ),
    "Télécommandes et claviers": (
        AssociationChoice("CLE 8000", "official:remote_X3D_direct"),
        AssociationChoice("TL 2000", "official:remote_X3D_direct"),
        AssociationChoice("TYXIA 1410", "official:remote_X3D_direct"),
    ),
    "Interrupteurs": (
        AssociationChoice("TYXIA 2310", "official:remote_X3D_direct"),
        AssociationChoice("TYXIA 2600", "official:remote_X3D_direct"),
        AssociationChoice("TYXIA 2700", "official:remote_X3D_direct"),
    ),
    "Capteurs": (
        AssociationChoice("SENSOR STI 2000", "official:sensor_X3D_direct"),
        AssociationChoice("TYBOX CONTROL", "official:sensor_X3D_direct"),
        AssociationChoice("TYBOX CONTROL XL", "official:sensor_X3D_direct"),
        AssociationChoice("Tysense Sun", "official:sensor_X3D_direct"),
        AssociationChoice("Tysense Thermo", "official:temperature_X3D_direct"),
        AssociationChoice("USAGE SENSOR DF", "official:detector_X3D_direct"),
        AssociationChoice("USAGE SENSOR DFR", "official:detector_X3D_direct"),
        AssociationChoice("USAGE WEATHER", "official:weather_plt"),
    ),
}


def get_association_choices(category: str) -> tuple[AssociationChoice, ...]:
    """Return official models, or generic recipes only when necessary."""
    official = OFFICIAL_ASSOCIATION_CATALOG.get(category, ())
    fallback = ASSOCIATION_CATALOG.get(category, ())
    if not official and not fallback:
        raise ValueError(f"Unknown TYDOM association category: {category}")

    # Do not make users choose a radio recipe when the official catalog knows
    # the exact physical product. Generic recipes remain only for categories
    # which have no catalogue-backed products (for example, legacy cameras).
    choices = official or fallback

    # A model can appear in multiple app catalog groups. HA Select options must
    # remain unique while preserving the official catalog ordering.
    return tuple({choice.label: choice for choice in choices}.values())


def get_install_payload(
    profile_id: str, network: int | None = None
) -> dict[str, str | int]:
    """Build a validated ``POST /devices`` discovery request body."""
    try:
        profile = (
            DISCOVERY_PROFILES.get(profile_id)
            or OFFICIAL_DISCOVERY_PROFILES[profile_id]
        )
    except KeyError as err:
        raise ValueError(f"Unknown TYDOM discovery profile: {profile_id}") from err
    payload: dict[str, str | int] = {
        "protocol": profile.protocol,
        "type": profile.type,
        "profile": profile.profile,
    }
    if network is not None:
        if network < 0:
            raise ValueError("TYDOM network must be a non-negative integer")
        payload["net"] = network
    elif profile.protocol == "ZIGBEE":
        payload["net"] = 0
    return payload


async def start_product_association(
    tydom_hub, profile_id: str, network: int | None = None
) -> dict[str, str | int]:
    """Start association through the physical gateway's LAN connection."""
    payload = get_install_payload(profile_id, network)
    local_hub = _get_local_association_hub(tydom_hub)
    await local_hub._tydom_client.post_device_discovery(payload)
    return payload


def _normalized_gateway_mac(gateway_mac: object) -> str:
    """Return a comparison-safe gateway MAC address."""
    return "".join(
        character for character in str(gateway_mac) if character.isalnum()
    ).upper()


def _get_local_association_hub(tydom_hub):
    """Prefer the matching LAN entry when the selected entry uses mediation.

    Radio discovery is a gateway-local operation. A user can legitimately have
    several distinct TYDOM installations in Home Assistant, so only an entry
    with the *same gateway MAC* may replace the selected entry. Keep the
    selected connection when there is no unambiguous local match: the official
    cloud workflow must keep working for cloud-only installations.
    """
    tydom_client = getattr(tydom_hub, "_tydom_client", None)
    if tydom_client is None:
        raise ValueError("The selected TYDOM gateway has no active client")
    if not getattr(tydom_client, "_remote_mode", False):
        return tydom_hub

    hass = getattr(tydom_hub, "_hass", None)
    gateway_mac = _normalized_gateway_mac(getattr(tydom_hub, "_mac", ""))
    if hass is not None and gateway_mac:
        local_hubs = [
            hub
            for hub in getattr(hass, "data", {}).get(DOMAIN, {}).values()
            if _normalized_gateway_mac(getattr(hub, "_mac", "")) == gateway_mac
            and not getattr(getattr(hub, "_tydom_client", None), "_remote_mode", True)
        ]
        if len(local_hubs) == 1:
            return local_hubs[0]

    return tydom_hub


async def remove_product_association(device) -> None:
    """Remove a product cleanly from the TYDOM gateway.

    A radio DELETE alone is insufficient for devices created as a
    ``relatedendpoints`` group (for example a TYXIA 2600): it leaves the
    group's configuration in the gateway.  The official application removes
    that group from both complete configuration files as well as deleting the
    radio product.  Ordinary products are deliberately rejected here until
    their references in user groups, scenarios and moments are handled too.
    """
    device_id = getattr(device, "_id", None)
    tydom_client = getattr(device, "_tydom_client", None)
    if device_id is None or tydom_client is None:
        raise ValueError("The selected entity does not expose a TYDOM device")
    if (
        getattr(device, "association_group_id", None) is None
        and not isinstance(device, TydomInterrupter)
    ):
        raise ValueError(
            "Safe complete removal is not yet available for this product. "
            "It may belong to user groups, scenarios or moments."
        )

    config = await tydom_client.get_config_file_document()
    groups = await tydom_client.get_groups_file_document()
    config_groups = config.get("groups")
    group_memberships = groups.get("groups")
    endpoints = config.get("endpoints")
    if not all(
        isinstance(value, list)
        for value in (config_groups, group_memberships, endpoints)
    ):
        raise ValueError("The gateway returned an incomplete configuration")

    association_group_id = getattr(device, "association_group_id", None)
    if association_group_id is None:
        # The official app can configure a single TYXIA 2600 button as an
        # interrupter without a related-endpoints group. It is safe to remove
        # only when it is the sole configured endpoint and has no membership.
        if not isinstance(device, TydomInterrupter):
            raise ValueError(
                "Safe complete removal is not yet available for this product. "
                "It may belong to user groups, scenarios or moments."
            )
        device_id = str(device_id)
        endpoint_id = str(getattr(device, "_endpoint", ""))
        matching_endpoints = [
            endpoint
            for endpoint in endpoints
            if isinstance(endpoint, dict)
            and str(endpoint.get("id_device")) == device_id
        ]
        referenced_by_group = any(
            isinstance(group, dict)
            and any(
                isinstance(member, dict) and str(member.get("id")) == device_id
                for member in group.get("devices", [])
            )
            for group in group_memberships
        )
        if (
            len(matching_endpoints) != 1
            or str(matching_endpoints[0].get("id_endpoint")) != endpoint_id
            or referenced_by_group
        ):
            raise ValueError(
                "Safe complete removal is only available for an isolated "
                "TYXIA 2600 interrupter button"
            )

        updated_config = copy.deepcopy(config)
        updated_config["endpoints"] = [
            endpoint for endpoint in endpoints if endpoint is not matching_endpoints[0]
        ]
        await tydom_client.post_config_file_document(updated_config)
        try:
            await tydom_client.delete_device(device_id)
        except Exception:
            try:
                await tydom_client.post_config_file_document(config)
            except Exception:
                LOGGER.exception("Unable to restore /configs/file after failed removal")
            raise
        return

    group_id = str(association_group_id)
    config_group = next(
        (
            group
            for group in config_groups
            if isinstance(group, dict) and str(group.get("id")) == group_id
        ),
        None,
    )
    group_membership = next(
        (
            group
            for group in group_memberships
            if isinstance(group, dict) and str(group.get("id")) == group_id
        ),
        None,
    )
    if config_group is None or group_membership is None:
        raise ValueError(
            "The dedicated association group is no longer present on the gateway"
        )
    if config_group.get("type") != "relatedendpoints":
        raise ValueError(
            "Safe complete removal is only available for dedicated "
            "related-endpoints groups"
        )

    device_id = str(device_id)
    member_ids = {
        str(member.get("id"))
        for member in group_membership.get("devices", [])
        if isinstance(member, dict) and member.get("id") is not None
    }
    if device_id not in member_ids:
        raise ValueError(
            "The selected product is not a member of its dedicated association group"
        )

    updated_config = copy.deepcopy(config)
    updated_config["groups"] = [
        group
        for group in config_groups
        if not (isinstance(group, dict) and str(group.get("id")) == group_id)
    ]
    updated_config["endpoints"] = [
        endpoint
        for endpoint in endpoints
        if not (
            isinstance(endpoint, dict) and str(endpoint.get("id_device")) == device_id
        )
    ]
    updated_groups = copy.deepcopy(groups)
    updated_groups["groups"] = [
        group
        for group in group_memberships
        if not (isinstance(group, dict) and str(group.get("id")) == group_id)
    ]

    # Nothing is deleted from the radio until the two source-of-truth files
    # have both been accepted.  If the second write or the radio DELETE fails,
    # restore the original documents so the official app keeps a coherent view.
    config_updated = False
    groups_updated = False
    try:
        await tydom_client.post_config_file_document(updated_config)
        config_updated = True
        await tydom_client.post_groups_file_document(updated_groups)
        groups_updated = True
        await tydom_client.delete_device(device_id)
    except Exception:
        if groups_updated:
            try:
                await tydom_client.post_groups_file_document(groups)
            except Exception:
                LOGGER.exception("Unable to restore /groups/file after failed removal")
        if config_updated:
            try:
                await tydom_client.post_config_file_document(config)
            except Exception:
                LOGGER.exception("Unable to restore /configs/file after failed removal")
        raise


def _next_interrupter_name(config: dict[str, object]) -> str:
    """Return the next official-style name for a standalone wall switch."""
    used_names = {
        str(endpoint.get("name"))
        for endpoint in config.get("endpoints", [])
        if isinstance(endpoint, dict)
    }
    number = 1
    while f"Interrupteur {number}" in used_names:
        number += 1
    return f"Interrupteur {number}"


def _new_related_endpoints_group_id(config: dict[str, object]) -> int:
    """Return an unused positive group id for a locally configured product."""
    existing_ids = {
        str(group.get("id"))
        for group in config.get("groups", [])
        if isinstance(group, dict) and group.get("id") is not None
    }
    while True:
        group_id = secrets.randbelow(2_147_483_646) + 1
        if str(group_id) not in existing_ids:
            return group_id


async def configure_tyxia_2600_interrupter(device, channel: str) -> str:
    """Add a discovered TYXIA 2600 output to an app-visible two-button group.

    Radio discovery alone creates an unconfigured X3D product. The first
    output becomes a draft; pairing the other output creates the configuration
    and membership records used by the official app for a complete TYXIA 2600.
    """
    if channel not in {"Bouton A", "Bouton B"}:
        raise ValueError(f"Unsupported TYXIA 2600 channel: {channel!r}")

    device_id = str(getattr(device, "_id", ""))
    endpoint_id = str(getattr(device, "_endpoint", ""))
    tydom_client = getattr(device, "_tydom_client", None)
    get_config = getattr(tydom_client, "get_config_file_document", None)
    post_config = getattr(tydom_client, "post_config_file_document", None)
    get_groups = getattr(tydom_client, "get_groups_file_document", None)
    post_groups = getattr(tydom_client, "post_groups_file_document", None)
    if (
        not device_id
        or not endpoint_id
        or not callable(get_config)
        or not callable(post_config)
    ):
        raise ValueError("The selected endpoint cannot be configured safely")

    config = await get_config()
    endpoints = config.get("endpoints") if isinstance(config, dict) else None
    if not isinstance(endpoints, list):
        raise TypeError("The gateway returned a malformed /configs/file document")
    if any(
        isinstance(endpoint, dict)
        and str(endpoint.get("id_device")) == device_id
        and str(endpoint.get("id_endpoint")) == endpoint_id
        for endpoint in endpoints
    ):
        raise ValueError("This TYXIA 2600 button is already configured")

    button = channel.removeprefix("Bouton ")
    endpoint_config = {
        "id_device": int(device_id),
        "id_endpoint": int(endpoint_id),
        "name": _next_interrupter_name(config),
        "picto": "default_device",
        "first_usage": "interrupter",
        "last_usage": "interrupter",
        "widget_behavior": {
            "action": "TOGGLE",
            "tutorial_id": f"switch_tyxia2600_btn_{button.lower()}",
        },
        "anticipation_start": False,
        "skill": "TYDOM_X3D",
        "space_id": "",
    }
    siblings = [
        endpoint
        for endpoint in endpoints
        if isinstance(endpoint, dict)
        and str(endpoint.get("id_device")) == device_id
        and endpoint.get("last_usage") == "interrupter"
    ]
    if not siblings:
        updated_config = copy.deepcopy(config)
        updated_config["endpoints"].append(endpoint_config)
        await post_config(updated_config)
        return str(endpoint_config["name"])

    if len(siblings) != 1 or not callable(get_groups) or not callable(post_groups):
        raise ValueError(
            "A complete TYXIA 2600 association requires one existing output "
            "and writable /groups/file support"
        )

    sibling = siblings[0]
    sibling_behavior = sibling.get("widget_behavior")
    sibling_tutorial = (
        sibling_behavior.get("tutorial_id")
        if isinstance(sibling_behavior, dict)
        else None
    )
    if sibling_tutorial is None:
        # The official app can create the initial standalone endpoint without
        # its tutorial metadata. The selected second output unambiguously
        # identifies the remaining first output.
        sibling_button = "B" if button == "A" else "A"
    elif not isinstance(sibling_tutorial, str) or not sibling_tutorial.startswith(
        "switch_tyxia2600_btn_"
    ):
        raise ValueError("The existing interrupter is not a TYXIA 2600 draft")
    else:
        sibling_button = sibling_tutorial.removeprefix(
            "switch_tyxia2600_btn_"
        ).upper()
    if sibling_button not in {"A", "B"} or sibling_button == button:
        raise ValueError("Select the other TYXIA 2600 button to complete the pair")

    groups = await get_groups()
    group_memberships = groups.get("groups") if isinstance(groups, dict) else None
    config_groups = config.get("groups")
    if not isinstance(group_memberships, list) or not isinstance(config_groups, list):
        raise TypeError("The gateway returned malformed association documents")

    name = str(sibling.get("name") or endpoint_config["name"])
    sibling_endpoint_id = sibling.get("id_endpoint")
    if sibling_endpoint_id is None:
        raise ValueError("The TYXIA 2600 draft has no endpoint id")
    group_id = _new_related_endpoints_group_id(config)

    updated_config = copy.deepcopy(config)
    for configured_endpoint in updated_config["endpoints"]:
        if (
            isinstance(configured_endpoint, dict)
            and str(configured_endpoint.get("id_device")) == device_id
            and str(configured_endpoint.get("id_endpoint")) == str(sibling_endpoint_id)
        ):
            configured_endpoint["name"] = f"CG_DD_COMMON_BUTTON{sibling_button}"
            configured_endpoint["widget_behavior"] = {
                "action": "TOGGLE",
                "tutorial_id": f"switch_tyxia2600_btn_{sibling_button.lower()}",
            }
    endpoint_config["name"] = f"CG_DD_COMMON_BUTTON{button}"
    updated_config["endpoints"].append(endpoint_config)
    updated_config["groups"].append(
        {
            "id": group_id,
            "name": name,
            "usage": "interrupter",
            "type": "relatedendpoints",
            "widget_behavior": {"tutorial_id": "switch_tyxia2600"},
        }
    )
    updated_groups = copy.deepcopy(groups)
    updated_groups["groups"].append(
        {
            "id": group_id,
            "devices": [
                {
                    "id": int(device_id),
                    "endpoints": [
                        {"id": int(sibling_endpoint_id)},
                        {"id": int(endpoint_id)},
                    ],
                }
            ],
        }
    )

    config_updated = False
    try:
        await post_config(updated_config)
        config_updated = True
        await post_groups(updated_groups)
    except Exception:
        if config_updated:
            try:
                await post_config(config)
            except Exception:
                LOGGER.exception("Unable to restore /configs/file after pairing failure")
        raise
    return name


class Hub:
    """Hub for Delta Dore Tydom."""

    manufacturer = "Delta Dore"

    def handle_event(self, event):
        """Event callback."""
        pass

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        host: str,
        mac: str,
        password: str,
        refresh_interval: str,
        zone_home: str,
        zone_away: str,
        zone_night: str,
        alarmpin: str,
    ) -> None:
        """Init hub."""
        self._host = host
        self._mac = mac
        self._pass = password
        self._refresh_interval = int(refresh_interval) * 60
        self._zone_home = zone_home
        self._zone_away = zone_away
        self._zone_night = zone_night
        self._pin = alarmpin
        self._hass = hass
        self._entry = entry
        self._name = mac
        self._id = "Tydom-" + mac[6:]
        self.devices = {}
        self.ha_devices = {}
        self.add_cover_callback = None
        self.add_sensor_callback = None
        self.add_climate_callback = None
        self.add_light_callback = None
        self.add_lock_callback = None
        self.add_alarm_callback = None
        self.add_update_callback = None
        self.add_weather_callback = None
        self.add_binary_sensor_callback = None
        self.add_scene_callback = None
        self.add_switch_callback = None
        self.add_button_callback = None
        self.add_number_callback = None
        self.add_select_callback = None
        self.add_event_callback = None

        self._tydom_client = TydomClient(
            hass=self._hass,
            id=self._id,
            mac=self._mac,
            host=self._host,
            password=self._pass,
            zone_home=self._zone_home,
            zone_away=self._zone_away,
            zone_night=self._zone_night,
            alarm_pin=self._pin,
            event_callback=self.handle_event,
        )

        self.online = True
        self._reload_button_created = False
        self._association_controls_created = False
        self._association_controls: list = []
        self._association_category = next(iter(ASSOCIATION_CATALOG))
        first_choice = get_association_choices(self._association_category)[0]
        self._association_product = first_choice.label
        self._association_profile = first_choice.profile_id
        self._association_channel = "Bouton A"
        self._pending_tyxia_2600_association: str | None = None
        self._refresh_energy_buttons_created: set[str] = set()
        self._device_association_buttons_created: set[tuple[str, str]] = set()
        self._remote_battery_entities: dict[str, HARemoteBattery] = {}
        self._interrupter_battery_entities: dict[str, HAInterrupterBattery] = {}
        self._twc_scene_sets: dict[str, dict[str, HAScene]] = {}
        self._twc_cover_entities: dict[str, HATwcShutterCover] = {}
        self._shutting_down = False

        # Polling cache for optimization
        self._polling_cache: dict[
            tuple[str, str], int
        ] = {}  # (device_key, attr_name) -> interval
        self._polling_cache_timestamp = 0
        self._polling_cache_ttl = 300  # 5 minutes
        self._next_poll_due: dict[int, float] = {}  # interval -> monotonic due time

        # Device factory registry for create_ha_device
        self._device_factories: dict[type, Callable] = {
            Tydom: self._create_tydom_device,
            TydomShutter: self._create_shutter_device,
            TydomEnergy: self._create_energy_device,
            TydomSmoke: self._create_smoke_device,
            TydomBoiler: self._create_boiler_device,
            TydomWindow: self._create_window_device,
            TydomDoor: self._create_door_device,
            TydomGate: self._create_gate_device,
            TydomGarage: self._create_garage_device,
            TydomLight: self._create_light_device,
            TydomSwitch: self._create_switch_device,
            TydomInterrupter: self._create_interrupter_device,
            TydomPlug: self._create_switch_device,
            TydomAlarm: self._create_alarm_device,
            TydomWeather: self._create_weather_device,
            TydomWater: self._create_water_device,
            TydomThermo: self._create_thermo_device,
            TydomSun: self._create_sun_device,
            TydomScene: self._create_scene_device,
            TydomGroup: self._create_group_device,
            TydomMoment: self._create_moment_device,
            TydomRemoteControl: self._create_remote_control_device,
            TydomDevice: self._create_generic_device,
        }

    def update_config(self, refresh_interval, zone_home, zone_away, zone_night):
        """Update zone configuration."""
        self._tydom_client.update_config(zone_home, zone_away, zone_night)
        self._refresh_interval = int(refresh_interval) * 60
        self._zone_home = zone_home
        self._zone_away = zone_away
        self._zone_night = zone_night

    @property
    def hub_id(self) -> str:
        """ID for dummy hub."""
        return self._id

    async def connect(self) -> ClientWebSocketResponse:
        """Connect to Tydom."""
        if self._shutting_down:
            raise asyncio.CancelledError()
        connection = await self._tydom_client.async_connect_and_initialise()
        if self._shutting_down:
            await self._tydom_client.async_disconnect()
            raise asyncio.CancelledError()
        return connection

    async def async_shutdown(self) -> None:
        """Stop background work and release the Tydom websocket."""
        if self._shutting_down:
            return
        self._shutting_down = True
        await self._tydom_client.async_disconnect()

    async def _interruptible_sleep(self, seconds: float) -> None:
        """Sleep in short slices so shutdown is picked up quickly."""
        remaining = seconds
        while remaining > 0 and not self._shutting_down:
            await asyncio.sleep(min(1.0, remaining))
            remaining -= 1.0

    @staticmethod
    async def get_tydom_credentials(
        session: ClientSession, email: str, password: str, macaddress: str
    ):
        """Get Tydom credentials."""
        return await TydomClient.async_get_credentials(
            session, email, password, macaddress
        )

    async def test_credentials(self) -> None:
        """Validate credentials."""
        connection = await self._tydom_client.async_connect()
        if hasattr(connection, "close"):
            try:
                await asyncio.wait_for(connection.close(), timeout=3.0)
            except TimeoutError:
                LOGGER.warning(
                    "Timed out closing Tydom websocket after credential test"
                )

    async def async_set_local_gateway_password(
        self, password: str, local_host: str | None = None
    ) -> None:
        """Change the local authentication secret, optionally via a LAN host."""
        if not self._tydom_client._remote_mode or not local_host:
            await self._tydom_client.async_set_local_gateway_password(password)
            self._pass = password
            return

        # The configured connection may use Delta Dore mediation, while this
        # endpoint is deliberately LAN-only. Reuse its already retrieved
        # gateway credential for one short-lived direct connection instead of
        # requiring the user to remove and reconfigure the integration.
        local_client = TydomClient(
            hass=self._hass,
            id=self._id,
            mac=self._mac,
            host=local_host,
            password=self._pass,
            zone_home=self._zone_home,
            zone_away=self._zone_away,
            zone_night=self._zone_night,
            alarm_pin=self._pin,
        )
        connection = await local_client.async_connect()
        local_client._connection = connection
        local_client._connection_ready = True

        async def consume_responses() -> None:
            while not local_client._shutting_down:
                await local_client.consume_messages()

        consumer_task = asyncio.create_task(consume_responses())
        try:
            await local_client.async_set_local_gateway_password(password)
        finally:
            consumer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await consumer_task
            await local_client.async_disconnect()

        self._pass = password

    def ready(self) -> bool:
        """Check if we're ready to work."""
        # and self.add_alarm_callback is not None
        is_ready = (
            self.add_cover_callback is not None
            and self.add_sensor_callback is not None
            and self.add_climate_callback is not None
            and self.add_light_callback is not None
            and self.add_lock_callback is not None
            and self.add_update_callback is not None
            and self.add_alarm_callback is not None
            and self.add_weather_callback is not None
            and self.add_scene_callback is not None
            and self.add_switch_callback is not None
            and self.add_button_callback is not None
            and self.add_number_callback is not None
            and self.add_select_callback is not None
            and self.add_event_callback is not None
            and self.add_binary_sensor_callback is not None
        )
        # Créer le bouton de rechargement une fois que les callbacks sont prêts
        if (
            is_ready
            and not self._reload_button_created
            and self.add_button_callback is not None
        ):
            reload_button = HAReloadButton(self, self._hass)
            self.add_button_callback([reload_button])
            self._reload_button_created = True
            LOGGER.debug("Bouton de rechargement créé")
        if (
            is_ready
            and not self._association_controls_created
            and self.add_button_callback is not None
            and self.add_select_callback is not None
        ):
            self.add_select_callback(
                [
                    HAGatewayAssociationCategorySelect(self),
                    HAGatewayAssociationProductSelect(self),
                    HAGatewayAssociationChannelSelect(self),
                    HAGatewayAssociationUsageSelect(self),
                ]
            )
            self.add_button_callback(
                [
                    HAGatewayAssociationGuideButton(self),
                    HAGatewayStartAssociationButton(self),
                ]
            )
            self._association_controls_created = True
            LOGGER.debug("Gateway product-association controls created")
        return is_ready

    @property
    def association_categories(self) -> tuple[str, ...]:
        """Return the usage categories offered by gateway association."""
        return tuple(ASSOCIATION_CATALOG)

    @property
    def association_category(self) -> str:
        """Return the currently selected association category."""
        return self._association_category

    @property
    def association_product_labels(self) -> tuple[str, ...]:
        """Return product families for the selected category."""
        return tuple(
            choice.label
            for choice in get_association_choices(self._association_category)
        )

    @property
    def association_product_label(self) -> str:
        """Return the label of the currently selected product family."""
        return self._association_product

    @property
    def association_usage_labels(self) -> tuple[str, ...]:
        """Return only the official application usages for the selected model."""
        return tuple(
            category
            for category in ASSOCIATION_CATALOG
            if any(
                choice.label == self._association_product
                for choice in get_association_choices(category)
            )
        )

    @property
    def association_usage_label(self) -> str:
        """Return the currently selected application usage."""
        return self._association_category

    @property
    def association_product_supported(self) -> bool:
        """Whether the current choice has a documented local install profile."""
        return self._association_profile is not None

    @property
    def association_channel_labels(self) -> tuple[str, ...]:
        """Return independent physical channels for the selected product."""
        if self._association_product == "TYXIA 2600":
            return TYXIA_2600_ASSOCIATION_CHANNELS
        return ()

    @property
    def association_channel_label(self) -> str | None:
        """Return the selected physical channel, if this product has one."""
        if not self.association_channel_labels:
            return None
        return self._association_channel

    @property
    def association_instructions(self) -> tuple[str, ...]:
        """Return the app-derived procedure for the selected product/channel."""
        if self._association_product != "TYXIA 2600":
            return ()
        channel = self._association_channel
        return tuple(
            step.format(channel=channel, button=channel.removeprefix("Bouton "))
            for step in TYXIA_2600_ASSOCIATION_GUIDE
        )

    def register_association_control(self, entity) -> None:
        """Register a gateway control that needs selection-state updates."""
        if entity not in self._association_controls:
            self._association_controls.append(entity)

    def unregister_association_control(self, entity) -> None:
        """Forget a gateway control removed by Home Assistant."""
        if entity in self._association_controls:
            self._association_controls.remove(entity)

    def _notify_association_controls(self) -> None:
        """Update the category/product controls after a selection change."""
        for entity in self._association_controls:
            entity.async_write_ha_state()

    def set_association_category(self, category: str) -> None:
        """Choose a category and retain the model when it is valid there."""
        choices = get_association_choices(category)
        self._association_category = category
        choice = next(
            (choice for choice in choices if choice.label == self._association_product),
            choices[0],
        )
        self._association_product = choice.label
        self._association_profile = choice.profile_id
        self._ensure_association_channel()
        self._notify_association_controls()

    def set_association_product(self, label: str) -> None:
        """Choose one product family from the current category."""
        for choice in get_association_choices(self._association_category):
            if choice.label == label:
                self._association_product = label
                self._association_profile = choice.profile_id
                self._ensure_association_channel()
                self._notify_association_controls()
                return
        raise ValueError(
            f"{label!r} is not available for {self._association_category!r}"
        )

    def set_association_usage(self, category: str) -> None:
        """Choose a documented usage compatible with the selected product."""
        if category not in self.association_usage_labels:
            raise ValueError(
                f"{category!r} is not available for {self._association_product!r}"
            )
        choice = next(
            choice
            for choice in get_association_choices(category)
            if choice.label == self._association_product
        )
        self._association_category = category
        self._association_profile = choice.profile_id
        self._notify_association_controls()

    def _ensure_association_channel(self) -> None:
        """Keep the selected physical channel valid after a product change."""
        choices = self.association_channel_labels
        if choices and self._association_channel not in choices:
            self._association_channel = choices[0]

    def set_association_channel(self, channel: str) -> None:
        """Choose a documented physical channel for the selected product."""
        if channel not in self.association_channel_labels:
            raise ValueError(
                f"{channel!r} is not available for {self._association_product!r}"
            )
        self._association_channel = channel
        self._notify_association_controls()

    async def start_selected_product_association(self) -> None:
        """Start association using the product selected in the gateway controls."""
        if self._association_profile is None:
            raise ValueError(
                "The selected category has no documented local TYDOM install profile"
            )
        payload = await start_product_association(self, self._association_profile)
        if (
            self._association_product == "TYXIA 2600"
            and self._association_category == "Interrupteurs"
        ):
            self._pending_tyxia_2600_association = self._association_channel
        else:
            self._pending_tyxia_2600_association = None
        LOGGER.info(
            "Started gateway association for %s on config entry %s",
            payload,
            self._entry.entry_id,
        )

    def _add_discovered_entities(self, entities: list) -> None:
        """Add discovered entities to the platform matching their entity type."""
        binary_sensors = [
            entity for entity in entities if isinstance(entity, BinarySensorEntity)
        ]
        sensors = [
            entity for entity in entities if not isinstance(entity, BinarySensorEntity)
        ]

        if sensors and self.add_sensor_callback is not None:
            self.add_sensor_callback(sensors)
        if binary_sensors and self.add_binary_sensor_callback is not None:
            self.add_binary_sensor_callback(binary_sensors)

    async def setup(self, connection: ClientWebSocketResponse) -> None:
        """Listen to tydom events."""
        # wait for callbacks to become available
        while not self.ready():
            if self._shutting_down:
                return
            await asyncio.sleep(1)
        LOGGER.debug("Listen to tydom events")

        # Validate data consistency after initial setup
        await self._validate_data_consistency()
        while not self._shutting_down:
            devices = await self._tydom_client.consume_messages()
            if self._shutting_down:
                return
            if devices is not None:
                for device in devices:
                    if device.device_id not in self.devices:
                        self.devices[device.device_id] = device
                        STRUCTURED_LOGGER.device_operation(
                            "debug",
                            "create",
                            device.device_id,
                            type=device.device_type,
                            name=device.device_name,
                        )
                        await self.create_ha_device(device)
                    else:
                        # Check for collision: same device_id but different device
                        stored_device = self.devices[device.device_id]
                        if stored_device is not device and (
                            stored_device.device_name != device.device_name
                            or stored_device.device_type != device.device_type
                        ):
                            # Resolve collision: update stored device with new data
                            STRUCTURED_LOGGER.device_operation(
                                "warning",
                                "collision_resolved",
                                device.device_id,
                                stored_name=stored_device.device_name,
                                stored_type=stored_device.device_type,
                                new_name=device.device_name,
                                new_type=device.device_type,
                                action="updating_existing",
                            )

                            # Update stored device attributes to match new device
                            # This ensures consistency and prevents future collisions
                            if hasattr(stored_device, "_name"):
                                stored_device._name = device.device_name
                            if hasattr(stored_device, "_type"):
                                stored_device._type = device.device_type

                            # Also update metadata if available
                            if (
                                hasattr(device, "_metadata")
                                and device._metadata is not None
                            ):
                                if hasattr(stored_device, "_metadata"):
                                    stored_device._metadata = device._metadata

                        LOGGER.debug(
                            "update device %s : %s",
                            device.device_id,
                            self.devices[device.device_id],
                        )
                        await self.update_ha_device(
                            self.devices[device.device_id], device
                        )
                self._refresh_group_members()

    def _refresh_group_members(self) -> None:
        """Resolve group members again after each protocol message batch."""
        for device in self.devices.values():
            if not isinstance(device, TydomGroup):
                continue
            ha_device = getattr(device, "_ha_device", None)
            if ha_device is not None and hasattr(ha_device, "refresh_members"):
                ha_device.refresh_members()

    async def create_ha_device(self, device: TydomDevice) -> None:
        """Create a new HA device using factory pattern.

        This method uses a factory pattern to delegate device-specific creation
        logic to specialized methods. This improves maintainability and reduces
        complexity compared to a large match/case statement.

        Args:
            device: TydomDevice instance to create Home Assistant entity for

        Raises:
            None: Exceptions are caught and logged, but do not propagate

        """
        device_type = type(device)
        factory = self._device_factories.get(device_type)

        if factory is None:
            LOGGER.error(
                "Unsupported device type: %s for device %s",
                device_type.__name__,
                device.device_id,
            )
            return

        try:
            await factory(device)
            self._maybe_create_device_association_buttons(device)
        except Exception as e:
            LOGGER.exception(
                "Error creating HA device for %s (%s): %s",
                device.device_id,
                device_type.__name__,
                e,
            )

    async def _create_tydom_device(self, device: Tydom) -> None:
        """Create Tydom gateway device."""
        LOGGER.debug("Create Tydom gateway %s", device.device_id)
        self.devices[device.device_id] = device
        ha_device = HATydom(device, self._hass)
        self.ha_devices[device.device_id] = ha_device
        if self.add_update_callback is not None:
            self.add_update_callback([ha_device])
        self._add_discovered_entities(ha_device.get_sensors())
        # Le bouton de rechargement est créé dans ready() pour être toujours présent

    async def _create_shutter_device(self, device: TydomShutter) -> None:
        """Create shutter/cover device."""
        LOGGER.debug("Create cover %s", device.device_id)
        ha_device = HACover(device, self._hass)
        self.ha_devices[device.device_id] = ha_device
        if self.add_cover_callback is not None:
            self.add_cover_callback([ha_device])
        self._add_discovered_entities(ha_device.get_sensors())

    async def _create_energy_device(self, device: TydomEnergy) -> None:
        """Create energy consumption device."""
        LOGGER.debug("Create conso %s", device.device_id)
        ha_device = HAEnergy(device, self._hass)
        self.ha_devices[device.device_id] = ha_device
        # HAEnergy itself carries no device_class/unit/value: it only groups
        # the per-attribute sensors below and must not be added as an entity,
        # or it shows up as a useless "unknown" sensor (e.g. sensor.tywatt_tywatt).
        self._add_discovered_entities(ha_device.get_sensors())
        # The device has no energy* attribute yet at first discovery (they only
        # appear once the first cdata poll response is parsed), so this rarely
        # creates the button here -- update_ha_device() does it once data arrives.
        self._maybe_create_refresh_energy_button(device, ha_device)

    def _maybe_create_refresh_energy_button(
        self, device: TydomEnergy, ha_device: HAEnergy
    ) -> None:
        """Create one on-demand refresh button per real Tywatt device.

        Some TydomEnergy devices only carry outTemperature (e.g. an outdoor
        probe reusing this class), not real Tywatt consumption data -- only
        attach the button to a device that actually exposes one of the polled
        cdata attributes (energyIndex/energyInstant/energyHisto/energyDistrib),
        or it ends up on the wrong HA device.
        """
        has_energy_attrs = any(
            key.startswith("energy") for key in vars(device) if not key.startswith("_")
        )
        device_key = device.device_id
        if (
            has_energy_attrs
            and device_key not in self._refresh_energy_buttons_created
            and self.add_button_callback is not None
        ):
            refresh_energy_button = HARefreshEnergyButton(self, self._hass, ha_device)
            self.add_button_callback([refresh_energy_button])
            self._refresh_energy_buttons_created.add(device_key)
            LOGGER.debug("Created energy refresh button for %s", device_key)

    async def _create_smoke_device(self, device: TydomSmoke) -> None:
        """Create smoke detector device."""
        LOGGER.debug("Create smoke %s", device.device_id)
        ha_device = HASmoke(device, self._hass)
        self.ha_devices[device.device_id] = ha_device
        self._add_discovered_entities([ha_device, *ha_device.get_sensors()])

    async def _create_boiler_device(self, device: TydomBoiler) -> None:
        """Create boiler/climate device."""
        LOGGER.debug("Create boiler %s", device.device_id)
        ha_device = HaClimate(device, self._hass)
        self.ha_devices[device.device_id] = ha_device
        if self.add_climate_callback is not None:
            self.add_climate_callback([ha_device])
        self._add_discovered_entities(ha_device.get_sensors())

    async def _create_window_device(self, device: TydomWindow) -> None:
        """Create window device (cover if motorized, else binary_sensor)."""
        LOGGER.debug("Create window %s", device.device_id)

        # Décision automatique selon les attributs du device
        if any(
            hasattr(device, a) for a in ["position", "positionCmd", "level", "levelCmd"]
        ):
            LOGGER.debug(
                "Window %s has motor control → adding as cover",
                device.device_id,
            )
            ha_device = HaWindow(device, self._hass)
            if self.add_cover_callback:
                self.add_cover_callback([ha_device])
        else:
            LOGGER.debug(
                "Window %s is passive → adding as binary_sensor",
                device.device_id,
            )
            ha_device = HaWindowOpening(device, self._hass)
            if self.add_binary_sensor_callback:
                self.add_binary_sensor_callback([ha_device])

        self.ha_devices[device.device_id] = ha_device
        self._add_discovered_entities(ha_device.get_sensors())

    async def _create_door_device(self, device: TydomDoor) -> None:
        """Create door device (cover if motorized, else binary_sensor)."""
        LOGGER.debug("Create door %s", device.device_id)

        # Décision automatique selon les attributs du device
        # podPosition : attribut utilisé par les portes motorisées KLINE
        # (device_type "belmDoor" / "klineDoor"), en lecture/écriture avec
        # les valeurs OPEN / CLOSE / LOCK.
        if any(
            hasattr(device, a)
            for a in [
                "position",
                "positionCmd",
                "level",
                "levelCmd",
                "podPosition",
            ]
        ):
            LOGGER.debug(
                "Door %s has motor control → adding as cover", device.device_id
            )
            ha_device = HaDoor(device, self._hass)
            if self.add_cover_callback:
                self.add_cover_callback([ha_device])
        else:
            LOGGER.debug(
                "Door %s is passive → adding as binary_sensor", device.device_id
            )
            ha_device = HaDoorOpening(device, self._hass)
            if self.add_binary_sensor_callback:
                self.add_binary_sensor_callback([ha_device])

        self.ha_devices[device.device_id] = ha_device
        self._add_discovered_entities(ha_device.get_sensors())

    async def _create_gate_device(self, device: TydomGate) -> None:
        """Create gate device."""
        LOGGER.debug("Create gate %s", device.device_id)
        if device.is_toggle_only:
            ha_device = HAButton(
                device,
                self._hass,
                "Toggle",
                "toggle",
                icon="mdi:gate",
                primary=True,
            )
            if self.add_button_callback is not None:
                self.add_button_callback([ha_device])
        else:
            ha_device = HaGate(device, self._hass)
            if self.add_cover_callback is not None:
                self.add_cover_callback([ha_device])
        self.ha_devices[device.device_id] = ha_device
        self._add_discovered_entities(ha_device.get_sensors())

    async def _create_garage_device(self, device: TydomGarage) -> None:
        """Create garage device."""
        LOGGER.debug("Create garage %s", device.device_id)
        if device.is_toggle_only:
            ha_device = HAButton(
                device,
                self._hass,
                "Toggle",
                "toggle",
                icon="mdi:garage",
                primary=True,
            )
            if self.add_button_callback is not None:
                self.add_button_callback([ha_device])
        else:
            ha_device = HaGarage(device, self._hass)
            if self.add_cover_callback is not None:
                self.add_cover_callback([ha_device])
        self.ha_devices[device.device_id] = ha_device
        self._add_discovered_entities(ha_device.get_sensors())

    async def _create_light_device(self, device: TydomLight) -> None:
        """Create light device."""
        LOGGER.debug("Create light %s", device.device_id)
        ha_device = HaLight(device, self._hass)
        self.ha_devices[device.device_id] = ha_device
        if self.add_light_callback is not None:
            self.add_light_callback([ha_device])
        self._add_discovered_entities(ha_device.get_sensors())

    async def _create_interrupter_device(self, device: TydomInterrupter) -> None:
        """Create a wall-switch event entity and one battery diagnostic."""
        LOGGER.debug("Create wall-switch button %s", device.device_id)
        ha_device = HAInterrupterEvent(device, self._hass)
        self.ha_devices[device.device_id] = ha_device
        if self.add_event_callback is not None:
            self.add_event_callback([ha_device])

        battery = self._interrupter_battery_entities.get(device.physical_device_id)
        if battery is None:
            battery = HAInterrupterBattery(device, self._hass)
            self._interrupter_battery_entities[device.physical_device_id] = battery
            if self.add_binary_sensor_callback is not None:
                self.add_binary_sensor_callback([battery])
        else:
            battery.add_device(device)

    async def _create_switch_device(self, device: TydomPlug | TydomSwitch) -> None:
        """Create a switch device for a controllable binary output."""
        LOGGER.debug("Create switch %s", device.device_id)
        ha_device = HASwitch(device, self._hass)
        self.ha_devices[device.device_id] = ha_device
        if self.add_switch_callback is not None:
            self.add_switch_callback([ha_device])
        self._add_discovered_entities(ha_device.get_sensors())

    async def _create_alarm_device(self, device: TydomAlarm) -> None:
        """Create alarm device."""
        LOGGER.debug("Create alarm %s", device.device_id)
        ha_device = HaAlarm(device, self._hass)
        self.ha_devices[device.device_id] = ha_device
        if self.add_alarm_callback is not None:
            self.add_alarm_callback([ha_device])
        if self.add_button_callback is not None:
            self.add_button_callback([HAAlarmAcknowledgeButton(device, self._hass)])
        self._add_discovered_entities(
            [
                HAAlarmPendingEventsSensor(device, self._hass),
                *ha_device.get_sensors(),
            ]
        )

    async def _create_weather_device(self, device: TydomWeather) -> None:
        """Create weather device."""
        LOGGER.debug("Create weather %s", device.device_id)
        ha_device = HaWeather(device, self._hass)
        self.ha_devices[device.device_id] = ha_device
        if self.add_weather_callback is not None:
            self.add_weather_callback([ha_device])
        self._add_discovered_entities(ha_device.get_sensors())

    async def _create_water_device(self, device: TydomWater) -> None:
        """Create water/moisture device."""
        LOGGER.debug("Create moisture %s", device.device_id)
        ha_device = HaMoisture(device, self._hass)
        self.ha_devices[device.device_id] = ha_device
        self._add_discovered_entities([ha_device, *ha_device.get_sensors()])

    async def _create_thermo_device(self, device: TydomThermo) -> None:
        """Create thermostat device."""
        LOGGER.debug("Create thermo %s", device.device_id)
        ha_device = HaThermo(device, self._hass)
        self.ha_devices[device.device_id] = ha_device
        self._add_discovered_entities([ha_device, *ha_device.get_sensors()])

    async def _create_sun_device(self, device: TydomSun) -> None:
        """Create a Tysense Sun irradiance sensor."""
        LOGGER.debug("Create Tysense Sun %s", device.device_id)
        ha_device = HaSun(device, self._hass)
        self.ha_devices[device.device_id] = ha_device
        self._add_discovered_entities([ha_device, *ha_device.get_sensors()])

    async def _create_scene_device(self, device: TydomScene) -> None:
        """Create a normal scene or aggregate TWC commands into one cover."""
        LOGGER.debug("Create scene %s", device.device_id)
        ha_device = HAScene(device, self._hass)
        self.ha_devices[device.device_id] = ha_device
        action = ha_device.twc_action
        if action is None:
            if self.add_scene_callback is not None:
                self.add_scene_callback([ha_device])
            return

        zone_key = ha_device._get_zone_from_scene()
        controller_id = ha_device._find_tywell_device(zone_key)
        parent_key = controller_id or f"tywell_control_{zone_key or 'default'}"
        grouping_key = f"{parent_key}:{zone_key or 'default'}"
        scenes = self._twc_scene_sets.setdefault(grouping_key, {})
        scenes[action] = ha_device

        cover = self._twc_cover_entities.get(grouping_key)
        if cover is None:
            cover = HATwcShutterCover(
                grouping_key,
                scenes,
                ha_device,
                self._hass,
                zone_key,
            )
            self._twc_cover_entities[grouping_key] = cover
            self.ha_devices[f"twc_cover_{grouping_key}"] = cover
            if self.add_cover_callback is not None:
                self.add_cover_callback([cover])
            LOGGER.debug(
                "Created Tywell shutter cover %s from scenario %s",
                grouping_key,
                device.device_name,
            )
        else:
            cover.refresh_scenes(ha_device)

    async def _create_group_device(self, device: TydomGroup) -> None:
        """Create a native Home Assistant entity for a controllable group."""
        LOGGER.debug("Create %s group %s", device.group_usage, device.device_id)
        if device.group_usage == "light":
            ha_device = HALightGroup(device, self._hass)
            callback = self.add_light_callback
        elif device.group_usage in {"awning", "shutter"}:
            ha_device = HACoverGroup(device, self._hass)
            callback = self.add_cover_callback
        elif device.group_usage == "plug":
            ha_device = HASwitchGroup(device, self._hass)
            callback = self.add_switch_callback
        else:
            LOGGER.debug(
                "Ignore unsupported group %s (%s)",
                device.device_id,
                device.group_usage,
            )
            return

        self.ha_devices[device.device_id] = ha_device
        if callback is not None:
            callback([ha_device])

    async def _create_moment_device(self, device: TydomMoment) -> None:
        """Create moment device."""
        LOGGER.debug("Create moment %s", device.device_id)
        ha_device = HAMoment(device, self._hass)
        self.ha_devices[device.device_id] = ha_device
        if self.add_switch_callback is not None:
            self.add_switch_callback([ha_device])

    async def _create_remote_control_device(self, device: TydomRemoteControl) -> None:
        """Create an event entity for a remote button and one battery diagnostic."""
        LOGGER.debug("Create remote-control button %s", device.device_id)
        migrate_legacy_remote_endpoint(
            self._hass,
            self._entry.entry_id,
            device.device_id,
        )
        ha_device = HARemoteEvent(device, self._hass)
        self.ha_devices[device.device_id] = ha_device
        if self.add_event_callback is not None:
            self.add_event_callback([ha_device])

        battery = self._remote_battery_entities.get(device.physical_device_id)
        if battery is None:
            battery = HARemoteBattery(device, self._hass)
            self._remote_battery_entities[device.physical_device_id] = battery
            if self.add_binary_sensor_callback is not None:
                self.add_binary_sensor_callback([battery])
        else:
            battery.add_device(device)

    async def _create_generic_device(self, device: TydomDevice) -> None:
        """Create generic sensor device."""
        LOGGER.debug("Create generic sensor %s", device.device_id)
        primary_binary_attribute = next(
            (
                attribute
                for attribute in ("on", "state")
                if hasattr(device, attribute)
                and is_binary_attribute(device, attribute, getattr(device, attribute))
            ),
            None,
        )
        if primary_binary_attribute is not None:
            ha_device = HAGenericBinarySensor(
                device, self._hass, primary_binary_attribute
            )
        else:
            ha_device = HASensor(device, self._hass)
        self.ha_devices[device.device_id] = ha_device
        self._add_discovered_entities([ha_device, *ha_device.get_sensors()])

        # Try to detect if device should also be a switch
        # Check for on/off capabilities that aren't already handled
        if device.device_type not in ["light", "cover", "alarm"]:
            has_on_off = (
                hasattr(device, "level")
                or hasattr(device, "on")
                or hasattr(device, "state")
            )
            # Check if device has levelCmd or onCmd in metadata (writable)
            has_control = False
            if device._metadata is not None:
                for key in device._metadata:
                    if key.endswith("Cmd") or key in ["level", "on", "state"]:
                        has_control = True
                        break

            if has_on_off and has_control:
                LOGGER.debug(
                    "Device %s has on/off capabilities, creating switch",
                    device.device_id,
                )
                switch_device = HASwitch(device, self._hass)
                if self.add_switch_callback is not None:
                    self.add_switch_callback([switch_device])

    async def update_ha_device(self, stored_device, device):
        """Update HA device values."""
        try:
            await stored_device.update_device(device)
            ha_device = self.ha_devices[device.device_id]

            # Special handling for scenes: invalidate caches and recreate relations
            if isinstance(device, TydomScene) and isinstance(ha_device, HAScene):
                await ha_device.async_device_update(device)

            new_sensors = ha_device.get_sensors()
            if new_sensors:
                # add new sensors
                LOGGER.debug(
                    "Ajout de %d nouveau(x) capteur(s) pour le device %s: %s",
                    len(new_sensors),
                    device.device_id,
                    [s._attr_name for s in new_sensors],
                )
                self._add_discovered_entities(new_sensors)
            if isinstance(ha_device, HAEnergy):
                self._maybe_create_refresh_energy_button(stored_device, ha_device)
            self._maybe_create_device_association_buttons(stored_device)
            # ha_device.publish_updates()
            # ha_device.update()
        except KeyError as e:
            LOGGER.warning(
                "Device %s non trouvé dans ha_devices lors de la mise à jour: %s",
                device.device_id,
                e,
            )
        except Exception:
            LOGGER.exception(
                "Erreur lors de la mise à jour du device %s", device.device_id
            )

    def _maybe_create_device_association_buttons(self, device: TydomDevice) -> None:
        """Expose association and opt-in permanent-removal product controls."""
        if self.add_button_callback is None:
            return

        # Scenarios, moments and groups are configuration objects, not radio
        # products. In particular, TWC_UP/DOWN/STOP are three scenarios that
        # form one virtual shutter cover. Giving each of them product-removal
        # controls creates misleading device pages and can never remove a
        # physical product.
        if isinstance(device, (TydomScene, TydomMoment, TydomGroup)):
            return

        buttons = []
        finalization_key = (device.device_id, "finalize_tyxia_2600")
        if (
            finalization_key not in self._device_association_buttons_created
            and self._pending_tyxia_2600_association is not None
            and isinstance(device, TydomRemoteControl)
            and device.device_name.startswith("X3D remote control ")
        ):
            buttons.append(
                HATyxia2600FinalizeAssociationButton(
                    device,
                    self._hass,
                    self._pending_tyxia_2600_association,
                    self._finalize_tyxia_2600_association,
                )
            )
            self._device_association_buttons_created.add(finalization_key)
        removal_key = (device.device_id, "remove_association")
        if (
            removal_key not in self._device_association_buttons_created
            and getattr(device, "_id", None) is not None
            and callable(
                getattr(getattr(device, "_tydom_client", None), "delete_device", None)
            )
        ):
            buttons.append(
                HADeviceRemovalButton(device, self._hass, remove_product_association)
            )
            self._device_association_buttons_created.add(removal_key)

        for command in (ASSOCIATION_COMMAND, IDENTIFY_COMMAND):
            key = (device.device_id, command)
            if key in self._device_association_buttons_created:
                continue
            if not supports_command(device, command):
                continue
            buttons.append(HADeviceAssociationButton(device, self._hass, command))
            self._device_association_buttons_created.add(key)

        if buttons:
            self.add_button_callback(buttons)

    async def _finalize_tyxia_2600_association(
        self, device: TydomRemoteControl, channel: str
    ) -> None:
        """Persist the selected TYXIA 2600 button, then rebuild HA entities."""
        if channel != self._pending_tyxia_2600_association:
            raise ValueError("This TYXIA 2600 association is no longer pending")
        name = await configure_tyxia_2600_interrupter(device, channel)
        self._pending_tyxia_2600_association = None
        LOGGER.info("Configured TYXIA 2600 %s as %s", channel, name)
        await self.reload_devices()

    async def ping(self) -> None:
        """Periodically send pings."""
        while not self._shutting_down:
            await self._tydom_client.ping()
            await self._interruptible_sleep(30)

    async def refresh_all(self) -> None:
        """Periodically refresh all metadata and data.

        It allows new devices to be discovered.
        """
        while not self._shutting_down:
            await self._tydom_client.get_info()
            await self._tydom_client.put_api_mode()
            await self._tydom_client.post_refresh()
            await self._tydom_client.get_configs_file()
            await self._tydom_client.get_groups()
            await self._tydom_client.get_devices_meta()
            await self._tydom_client.get_devices_cmeta()
            await self._tydom_client.get_devices_data()
            await self._tydom_client.get_scenarii()
            await self._tydom_client.get_moments()
            await self._interruptible_sleep(600)

    async def refresh_data_1s(self) -> None:
        """Refresh data for devices in list."""
        while not self._shutting_down:
            await self._tydom_client.poll_devices_data_1s()
            await self._interruptible_sleep(1)

    def _rebuild_polling_cache(self) -> None:
        """Rebuild polling cache efficiently.

        This method scans all devices and their metadata to build a cache
        mapping (device_key, attribute_name) to polling intervals based on
        the validity metadata. The cache is rebuilt periodically to account
        for metadata changes.

        The cache structure: {(device_key, attr_name): interval_seconds}
        - Devices with validity=INFINITE or upToDate are not cached (no polling)
        - Devices with validity=ES_SUPERVISION are cached with 300s interval
        - Devices with validity=SENSOR_SUPERVISION are cached with 60s interval
        - Devices with validity=SYNCHRO_SUPERVISION are cached with 30s interval
        """
        new_cache: dict[tuple[str, str], int] = {}
        for device_key, device in self.devices.items():
            if not hasattr(device, "_metadata") or device._metadata is None:
                continue
            for attr_name, attr_metadata in device._metadata.items():
                if isinstance(attr_metadata, dict):
                    validity = attr_metadata.get("validity")
                    interval = get_polling_interval_for_validity(validity)
                    if interval is not None:
                        new_cache[(device_key, attr_name)] = interval

        # Update cache atomically
        self._polling_cache = new_cache
        LOGGER.debug("Polling cache rebuilt with %d entries", len(self._polling_cache))

    async def refresh_data(self) -> None:
        """Periodically refresh data for devices which don't do push.

        Uses adaptive polling based on validity metadata:
        - INFINITE/upToDate: No polling needed
        - ES_SUPERVISION: Poll every 5 minutes
        - SENSOR_SUPERVISION: Poll every 1 minute
        - SYNCHRO_SUPERVISION: Poll every 30 seconds

        The polling groups are rebuilt every 5 minutes to account for
        metadata changes.
        """
        while not self._shutting_down:
            current_time = time.monotonic()

            # Rebuild cache only if expired
            if current_time - self._polling_cache_timestamp > self._polling_cache_ttl:
                self._rebuild_polling_cache()
                self._polling_cache_timestamp = current_time

            # Group devices by interval from cache
            interval_groups: dict[int, set[str]] = {}
            for (device_key, _attr_name), interval in self._polling_cache.items():
                interval_groups.setdefault(interval, set()).add(device_key)

            active_intervals = set(interval_groups)
            self._next_poll_due = {
                interval: due
                for interval, due in self._next_poll_due.items()
                if interval in active_intervals
            }

            # Poll devices according to their intervals
            if interval_groups:
                # Sort intervals from shortest to longest
                sorted_intervals = sorted(interval_groups.keys())
                shortest_interval = sorted_intervals[0]

                # Poll every interval group whose due time has elapsed, not just
                # the shortest one - otherwise ES_SUPERVISION/SENSOR_SUPERVISION
                # devices are starved forever as soon as any device needs
                # SYNCHRO_SUPERVISION (shortest_interval always wins otherwise).
                for interval, device_keys in interval_groups.items():
                    if current_time < self._next_poll_due.get(interval, 0):
                        continue
                    self._next_poll_due[interval] = current_time + interval
                    for device_key in device_keys:
                        if device_key in self.devices:
                            device = self.devices[device_key]
                            if hasattr(device, "_tydom_client"):
                                try:
                                    await device._tydom_client.poll_device_data(
                                        device._id, device.device_endpoint
                                    )
                                except Exception as e:
                                    LOGGER.warning(
                                        "Error polling device %s: %s", device_key, e
                                    )

                # Sleep for the shortest interval so due longer-interval groups
                # still get checked promptly on the next wake-up.
                await self._interruptible_sleep(shortest_interval)
            else:
                # No devices need validity-based polling, use default refresh interval
                if self._refresh_interval > 0:
                    await self._interruptible_sleep(self._refresh_interval)
                else:
                    await self._interruptible_sleep(60)

    async def refresh_energy_now(self, device_id: str, endpoint_id: str | None) -> None:
        """Poll one Tywatt cdata endpoint immediately, on demand."""
        await self._tydom_client.poll_devices_data_5m(device_id, endpoint_id)

    async def refresh_cdata(self) -> None:
        """Periodically poll the cdata endpoints registered for devices like Tywatt.

        Endpoints such as energyIndex, energyInstant, energyHisto and
        energyDistrib are registered via add_poll_device_url_5m() while parsing
        /devices/cmeta (see MessageHandler.parse_cmeta_data) and must be polled
        on their own schedule. They must NOT be polled only from within
        refresh_data()'s "no validity-based polling needed" branch: as soon as
        any other device exposes validity metadata (the common case), that
        branch never runs and these cdata endpoints (e.g. the Tywatt instant
        consumption sensor) would never be queried.

        Poll once at startup, then follow the refresh interval selected in the
        integration options. The per-device Refresh button remains available
        for an immediate reading between scheduled polls.
        """
        while not self._shutting_down:
            try:
                await self._tydom_client.poll_devices_data_5m()
            except Exception:
                LOGGER.exception("Error polling registered cdata endpoints")
            await self._interruptible_sleep(self._refresh_interval)

    async def reload_devices(self) -> None:
        """Recharger tous les appareils et entités comme au démarrage initial.

        Cette méthode vide tous les appareils existants et les recharges depuis zéro.
        """
        LOGGER.info("Début du rechargement de tous les appareils")

        # Vider les dictionnaires d'appareils
        self.devices.clear()
        self.ha_devices.clear()
        self._remote_battery_entities.clear()
        self._interrupter_battery_entities.clear()
        self._twc_scene_sets.clear()
        self._twc_cover_entities.clear()
        # Réinitialiser le flag pour recréer le bouton après le rechargement
        self._reload_button_created = False
        self._association_controls_created = False
        self._association_controls.clear()
        self._refresh_energy_buttons_created.clear()
        self._device_association_buttons_created.clear()

        # Supprimer toutes les entités existantes via l'Entity Registry
        from homeassistant.helpers import entity_registry as er

        entity_registry = er.async_get(self._hass)
        entities_to_remove = []

        # Parcourir toutes les entités enregistrées pour cette intégration
        for entity_id, entity_entry in entity_registry.entities.items():
            if entity_entry.config_entry_id == self._entry.entry_id:
                entities_to_remove.append(entity_id)

        # Supprimer les entités
        for entity_id in entities_to_remove:
            entity_registry.async_remove(entity_id)

        LOGGER.info(
            "Suppression de %d entité(s) existante(s) et rechargement des appareils",
            len(entities_to_remove),
        )

        # Recharger toutes les métadonnées et données comme au démarrage
        await self._tydom_client.get_info()
        await self._tydom_client.put_api_mode()
        await self._tydom_client.post_refresh()
        await self._tydom_client.get_configs_file()
        await self._tydom_client.get_groups()
        # Association and removal change the gateway inventory. A user-triggered
        # reload must bypass the one-hour metadata cache or newly associated
        # products remain invisible until that cache expires.
        await self._tydom_client.get_devices_meta(force_refresh=True)
        await self._tydom_client.get_devices_cmeta(force_refresh=True)
        await self._tydom_client.get_devices_data()
        await self._tydom_client.get_scenarii()
        await self._tydom_client.get_moments()

        # Recréer le bouton de rechargement après le rechargement
        # (le bouton d'actualisation énergie est recréé par _create_energy_device
        # quand le device Tywatt est redécouvert)
        if self.add_button_callback is not None:
            reload_button = HAReloadButton(self, self._hass)
            self.add_button_callback([reload_button])
            LOGGER.debug("Bouton de rechargement recréé après le rechargement")
        if (
            self.add_button_callback is not None
            and self.add_select_callback is not None
        ):
            self.add_select_callback(
                [
                    HAGatewayAssociationCategorySelect(self),
                    HAGatewayAssociationProductSelect(self),
                    HAGatewayAssociationChannelSelect(self),
                    HAGatewayAssociationUsageSelect(self),
                ]
            )
            self.add_button_callback(
                [
                    HAGatewayAssociationGuideButton(self),
                    HAGatewayStartAssociationButton(self),
                ]
            )
            self._association_controls_created = True

        LOGGER.info(
            "Rechargement terminé, les nouveaux appareils seront découverts automatiquement"
        )

        # Validate data consistency after reload
        await self._validate_data_consistency()

    async def _validate_data_consistency(self) -> None:
        """Validate data consistency: check that devices in groups exist, scenarios reference valid devices."""
        LOGGER.debug("Validating data consistency...")

        issues = []

        # Check groups: verify that all device IDs in groups exist
        for device_id, device in self.devices.items():
            if isinstance(device, TydomGroup):
                for group_device_id in device.device_ids:
                    if group_device_id not in self.devices:
                        # Try to find by various ID formats
                        found = False
                        for _id, _device in self.devices.items():
                            if (
                                _id == group_device_id
                                or str(getattr(_device, "device_id", ""))
                                == group_device_id
                                or str(getattr(_device, "_id", "")) == group_device_id
                            ):
                                found = True
                                break

                        if not found:
                            issues.append(
                                f"Group {device.device_name} ({device_id}) references non-existent device: {group_device_id}"
                            )

        # Check scenarios: verify that grpAct and epAct reference valid devices/groups
        for device_id, device in self.devices.items():
            if isinstance(device, TydomScene):
                # Check grpAct
                grp_act = getattr(device, "grpAct", None)
                if grp_act and isinstance(grp_act, list):
                    from .tydom.MessageHandler import groups_data

                    for grp_action in grp_act:
                        if isinstance(grp_action, dict):
                            grp_id = grp_action.get("id")
                            if grp_id:
                                grp_id_str = str(grp_id)
                                # All groups remain in protocol metadata even
                                # when no Home Assistant control is appropriate.
                                if grp_id_str not in groups_data:
                                    issues.append(
                                        f"Scene {device.device_name} ({device_id}) references non-existent group: {grp_id_str}"
                                    )

                # Check epAct
                ep_act = getattr(device, "epAct", None)
                if ep_act and isinstance(ep_act, list):
                    for ep_action in ep_act:
                        if isinstance(ep_action, dict):
                            ep_id = ep_action.get("id")
                            if ep_id:
                                ep_id_str = str(ep_id)
                                # Check if device/endpoint exists
                                device_found = False
                                for _id, _device in self.devices.items():
                                    if (
                                        _id == ep_id_str
                                        or str(getattr(_device, "device_id", ""))
                                        == ep_id_str
                                        or str(getattr(_device, "_id", "")) == ep_id_str
                                    ):
                                        device_found = True
                                        break

                                if not device_found:
                                    issues.append(
                                        f"Scene {device.device_name} ({device_id}) references non-existent device/endpoint: {ep_id_str}"
                                    )

        # Log issues
        if issues:
            LOGGER.warning(
                "Found %d data consistency issue(s):",
                len(issues),
            )
            for issue in issues:
                LOGGER.warning("  - %s", issue)
        else:
            LOGGER.debug("Data consistency validation passed: no issues found")
