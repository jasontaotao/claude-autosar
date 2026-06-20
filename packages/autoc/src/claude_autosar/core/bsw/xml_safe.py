"""XXE-safe XML parsing helpers for lxml.

All ``etree.parse`` / ``etree.fromstring`` calls in this project should go
through the helpers provided here to prevent XML External Entity (XXE)
injection.  The defaults harden the parser against:

* entity expansion attacks  (``resolve_entities=False``)
* network-based XXE         (``no_network=True``)
* DTD-based attacks         (``dtd_validation=False``, ``load_dtd=False``)

Callers may override most settings via ``**kwargs``, but
``resolve_entities`` is **always forced to False** regardless of caller input.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lxml import etree


def _safe_parser(**kwargs: Any) -> etree.XMLParser:
    """Return an ``XMLParser`` with XXE-safe defaults.

    Default settings (overridable via *kwargs*):

    * ``resolve_entities=False``  — **always forced**, cannot be overridden
    * ``no_network=True``
    * ``dtd_validation=False``
    * ``load_dtd=False``
    * ``huge_tree=True``
    * ``recover=True``

    Parameters
    ----------
    **kwargs
        Extra keyword arguments forwarded to ``etree.XMLParser``.
        ``resolve_entities`` is silently overridden to ``False`` even if
        the caller passes a different value.

    Returns
    -------
    etree.XMLParser
    """
    defaults: dict[str, Any] = {
        "resolve_entities": False,
        "no_network": True,
        "dtd_validation": False,
        "load_dtd": False,
        "huge_tree": True,
        "recover": True,
    }
    defaults.update(kwargs)
    # resolve_entities is a hard constraint — never allow True
    defaults["resolve_entities"] = False
    return etree.XMLParser(**defaults)


def _safe_parse(path: str | Path, **kwargs: Any) -> etree._ElementTree:
    """Parse an XML file with XXE-safe defaults.

    Parameters
    ----------
    path : str | Path
        Path to the XML file.
    **kwargs
        Forwarded to :func:`_safe_parser` (except ``resolve_entities``).

    Returns
    -------
    etree._ElementTree
    """
    parser = _safe_parser(**kwargs)
    return etree.parse(str(path), parser=parser)


def _safe_fromstring(text: str | bytes, **kwargs: Any) -> etree._Element:
    """Parse an XML string with XXE-safe defaults.

    Drop-in replacement for ``etree.fromstring()`` that uses a hardened
    parser internally.

    Parameters
    ----------
    text : str | bytes
        XML content to parse.
    **kwargs
        Forwarded to :func:`_safe_parser` (except ``resolve_entities``).

    Returns
    -------
    etree._Element
    """
    parser = _safe_parser(**kwargs)
    return etree.fromstring(text, parser=parser)


__all__ = ["_safe_parser", "_safe_parse", "_safe_fromstring"]
