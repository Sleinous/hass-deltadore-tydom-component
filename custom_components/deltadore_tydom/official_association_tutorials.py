"""French association tutorials extracted from the official TYDOM catalogue.

The compact payload contains the active product-to-tutorial mapping and the
French steps from TYDOM 4.20.02. It deliberately remains data-only: gateway
commands and device configuration continue to live in `hub`.
"""

from __future__ import annotations

import base64
import gzip
import json
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class OfficialAssociationStep:
    """One physical instruction and its matching Home Assistant action."""

    text: str
    starts_gateway_listening: bool = False


_COMPRESSED_CATALOG: Final = (
    "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"
)


def _load_tutorials() -> dict[str, tuple[OfficialAssociationStep, ...]]:
    """Decode the read-only official product tutorial catalogue."""
    payload = json.loads(
        gzip.decompress(base64.b64decode(_COMPRESSED_CATALOG)).decode("utf-8")
    )
    tutorials = payload["tutorials"]
    return {
        product: tuple(
            OfficialAssociationStep(
                text=step["text"],
                starts_gateway_listening=step["launch"],
            )
            for step in tutorials[tutorial_id]
            if step["text"]
        )
        for product, tutorial_id in payload["models"].items()
        if tutorial_id in tutorials and tutorials[tutorial_id]
    }


OFFICIAL_ASSOCIATION_TUTORIALS: Final = _load_tutorials()
