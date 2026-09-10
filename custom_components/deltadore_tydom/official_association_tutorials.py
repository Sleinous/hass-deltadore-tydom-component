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



# Official vector illustrations for the products requiring a channel-specific
# workflow. They are original Android Vector Drawable resources, compressed to
# keep the custom integration small. The converter below deliberately exposes
# only a safe SVG subset (paths and groups) through the authenticated HA view.
_COMPRESSED_COMPLEX_ILLUSTRATIONS: Final = (
    "H4sIAAAAAAAEAO19aY8bSZLlXwlovnawwo9w9yhgMTvoGWxh0Y35MINcQFuLQopSNYWmDihV7K4Z9H9fe888gsyDSWYmmUlK1tXF"
    "8gyPw/wyN3tm5vbfr77+9vXTl/eXy6tXP/73q69L33XdL2++fvzFvfrx/76aX369XH76yy9f5r/9sq5zv1x9fffZvfrDvfV+R33Y"
    "UR931Pc76tOr//eHzQb57Q3yOxrkdzTI72iQ39Egv6NBft0gVvz+9/eXLrptA7VZvWWsbt9yq3W3bwl3E3C7Yzert/Tt7VvuJcDf"
    "R0C4l4Cwm4Cwm4BwHwHxXgLibgLibgLimoD58l3ZukzHyr+++/3yzg/fuuHmZ2/dcHNi37rh5sy+dUN/k+xbc2bjkTe7yH6zi+w3"
    "u8h+s4vsN2uyr/72/ut8oYPhw12L7q47bq+77Xf5ve4KW4nxu4i5vQa337WLGL+FmFRH9nIrMfWO27Ny+11bibl2V9jrrrjXXbeH"
    "fGzYm10Nuz1vt9+1q2G3Z/D2u3Y1bNtczjtHLO81YnmvEct7jVjea8Ty/SOWd45Y3mvE8l4jlvcasbzXiOUbI/aPP7xavZuLgEbp"
    "7H5p7MdXP//WdWH+z3//sGxW775cvf/08X/8/MrNup9fNe8+zj+9ff/xL3Lht6+/tuXnV//Mu9/9/OXnj/qcfqi5/Pj2y6f3b39c"
    "vHv/l8VXud+7NOvevv8sbxnr/vb+7deFVIXc36xavX/3t8+fvnz9P5u33FH/07XX//wKdDSNkP7x6sd6r1Quvn79/OMPP1zNF+8+"
    "XF7NasVs/unDD5ef//rDl3dXP9RrP79at6eR/2mbPl9+XUyfxh//Kl0o7/2zD6lx3aId0rwtsxKbrnWpyTOX8F+XVi7FedewCleb"
    "8f8LeUIfkD/aWiXPXPg07/iqtr5F//96o+1XX798+uu7P35afvoiNPzPOQo//Pb+T+iJW7eNHejZfT/sbN2v75fLG69+80Uq//Xy"
    "y183Xn6tE1yc9b4Jw6J1Ifwxl1nM8leTUxPdLEYWohRW8uu89EdoPO7pUdnjWZQW8vA8zLpe+kQuhtbX6tCi+oKvkM5hReG1dqp9"
    "/djG3e63O5s2S5Gtm8vH0yDDHGclSytcryX5mVond/SoKrjajNVsnp9laZ38VVo8qyX5mRqHZ1HFq+1Y/frPxdUuvtFJzdRJ7MN1"
    "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"
    "O32QAgi47Hyp92fd9+Gs+/6caU9nTHw4556PL9bzd6NQj8P9o+H+x3GKNWjfoP3vANp/ok9seTsPcTCf2FP0iQ29zJ4Tg3UM0jHP"
    "UoNyzgbKMRjnQTDO40T43kT4o8W1+e4QcW15lOK9xbVZXNveFGhcWzzpuLa6mq6+Xn797erfvnwRvmXCvAnzhwhwO2HrsqkhpoaY"
    "GmJqyLephuzfZRbgZgFuFuBmAW4W4GYBbice4JYMJTOUzFAyQ8mehpJ93yiSYTGGxRgWY1iMYTGnahL2lpZsP2H32967LS3ZnU2z"
    "tGSWlszSkrWWlszSkrWWlszSkjWWlszSkllassbSkrWVsVpaMktLZmnJLC1ZY2nJWktL1lhastbSkllasv3gssdh9ZaW7HiOKZaW"
    "zBxTLC3ZKZ+qbFFb34C/zXXbvKUlM08h8xQyTyHzFLKoLYvasqgti9qyqC2L2rKorceAY5aW7OBHtdjZpTvAIju79Ds5u3TngjoH"
    "AO1+EO0ALbC0ZJaWzNKSnRv1lpbM0pJ9k4aTfVro6Cx8iiYIM0O8vBniNEwRZo44M3OEmSQeZZI4wH5qacksLdnjqLe0ZC9Fu6Ul"
    "eyHizz0tmbe0ZMd0ijVo36D97wDaf6JPrKUlO12f2DPJZGCQjnmWGpRzmlCOwTjPcAadpSU7XlybHbhscW3fyYHLlpbMhPkXF+Zv"
    "BridqHXZ1BBTQ0wNMTXk21RD9u8yC3CzADcLcLMANwtwswC3Ew9ws7RkhpIZSmYomaUlewyKZFiMYTGGxRgWY1jMaZqEf//7+0sX"
    "3UYaXstM9p1v35aZ7M6mWWYyy0xmmclay0xmmclay0xmmckay0xmmcksM1ljmcnaylgtM5llJrPMZJaZrLHMZK1lJmssM1lrmcks"
    "M9l+cNmj4XpLTnY89xRLTmbuKZac7NsL4npcE57p3J7wWDvK7iaE+DznJh2xCe6ZTm49YhPS8xx5dsQW+PQ8Z84dswnPc/jyfi34"
    "tv0J7goqTd+wL2De5oqmzk1H80RzaRAdZZBBzpy0mT7xADzo0qUFVeUVgMDshQ+Yh61awYielkpqwVwDfjQfDG4sdepxr5ae1FT1"
    "jREZTk0IOapxVNQlFgiWEv11eek1rADraNYP7B64huUVVDBarNS3f+6q3SmOylZYK1vDcf3DMISHdw+jvvzc7mGYc0+K1NvlHUMb"
    "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"
)

_ANDROID_NAMESPACE: Final = "{http://schemas.android.com/apk/res/android}"
_COLOURS: Final = {
    "@color/uiLight": "#ffffff",
    "@color/uiGray20": "#d6dde5",
    "@color/uiGray40": "#8a98a8",
    "@color/uiGray60": "#637386",
    "@color/uiGray80": "#536377",
    "@color/brandDark": "#344457",
    "@color/brandSecondary": "#2ab897",
    "@color/statusError": "#ef625f",
    "@color/statusWarning": "#f5b942",
}


def _load_complex_illustrations() -> tuple[dict[str, tuple[str, ...]], dict[str, str]]:
    """Decode the official channel-specific tutorial illustrations."""
    payload = json.loads(
        gzip.decompress(base64.b64decode(_COMPRESSED_COMPLEX_ILLUSTRATIONS)).decode(
            "utf-8"
        )
    )
    return (
        {key: tuple(value) for key, value in payload["tutorials"].items()},
        payload["vectors"],
    )


_COMPLEX_TUTORIAL_ILLUSTRATIONS, _COMPLEX_ILLUSTRATION_VECTORS = (
    _load_complex_illustrations()
)


def get_association_illustration_ids(tutorial_id: str | None) -> tuple[str, ...]:
    """Return the official illustration sequence for a selected channel."""
    if tutorial_id is None:
        return ()
    return _COMPLEX_TUTORIAL_ILLUSTRATIONS.get(tutorial_id, ())


def _android_attr(element, name: str) -> str | None:
    """Return an Android Vector Drawable attribute."""
    return element.attrib.get(f"{_ANDROID_NAMESPACE}{name}")


def _svg_colour(value: str | None, default: str) -> str:
    """Translate the small colour palette used by official vector resources."""
    if value is None:
        return default
    return _COLOURS.get(value, value)


def get_association_illustration_svg(image_id: str) -> str | None:
    """Convert one embedded Android vector to a browser-safe SVG document."""
    vector = _COMPLEX_ILLUSTRATION_VECTORS.get(image_id)
    if vector is None:
        return None

    from xml.etree import ElementTree
    from xml.sax.saxutils import escape

    root = ElementTree.fromstring(vector)
    viewport_width = _android_attr(root, "viewportWidth")
    viewport_height = _android_attr(root, "viewportHeight")
    if not viewport_width or not viewport_height:
        return None

    paths: list[str] = []
    for path in root.iter():
        if path.tag.rsplit("}", maxsplit=1)[-1] != "path":
            continue
        path_data = _android_attr(path, "pathData")
        if not path_data:
            continue
        fill = escape(_svg_colour(_android_attr(path, "fillColor"), "none"))
        stroke = escape(_svg_colour(_android_attr(path, "strokeColor"), "none"))
        attributes = [
            f'd="{escape(path_data)}"',
            f'fill="{fill}"',
            f'stroke="{stroke}"',
        ]
        if stroke != "none" and (width := _android_attr(path, "strokeWidth")):
            attributes.append(f'stroke-width="{escape(width)}"')
        if fill_type := _android_attr(path, "fillType"):
            attributes.append(
                'fill-rule="evenodd"' if fill_type == "evenOdd" else 'fill-rule="nonzero"'
            )
        paths.append(f"<path {' '.join(attributes)}/>")

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {escape(viewport_width)} {escape(viewport_height)}" '
        'role="img" aria-label="Illustration officielle Delta Dore">'
        f"{''.join(paths)}</svg>"
    )


def get_association_illustration_data_url(image_id: str) -> str | None:
    """Return an inline SVG URL usable by a Markdown notification."""
    svg = get_association_illustration_svg(image_id)
    if svg is None:
        return None
    encoded_svg = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded_svg}"
