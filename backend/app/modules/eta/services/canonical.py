"""
app.modules.eta.services.canonical — ETA Canonical Serialization Engine (FR-531)

Implements the Egyptian Tax Authority (ETA) e-Invoicing & e-Receipt canonical serialization
algorithm required for CAdES-BES electronic signing.

The 5 ETA Canonicalization Rules (Strictly Enforced):
1. Uppercase Keys: All property names must be converted to culture-invariant UPPERCASE.
2. Double Quotes: All property names and simple values (including numbers and booleans)
   MUST be enclosed in double quotes `"..."`.
3. Exact Values: Property values are taken exactly as they appear. `0.0` must serialize as `"0.0"`,
   not `"0"` or `"0.00"`. JSON numeric literals are parsed as strings to prevent Python from
   silently normalizing or rounding floats/ints.
4. The Array Rule (CRITICAL): In JSON, the entire array serialization is prefixed with the UPPERCASE
   array property name, AND every array element inside it is additionally preceded by that same
   UPPERCASE array property name.
   Example:
     `{"invoiceLines": [{"element": 1}, {"element": 2}]}`
     canonicalizes to:
     `"INVOICELINES""INVOICELINES""ELEMENT""1""INVOICELINES""ELEMENT""2"`
5. Document Order: Serialize in exact document insertion order.
"""
from __future__ import annotations

import json
from typing import Any


def serialize_document(json_payload: str | bytes | dict | list) -> str:
    """
    Serialize an incoming JSON document or Python structure into its canonical ETA string representation.

    If `json_payload` is a JSON string or raw bytes, it is parsed using `parse_float=str` and `parse_int=str`
    so that numeric literals remain exact strings (e.g., `0.0` does not become `0` or `0.00`).

    Args:
        json_payload: The JSON document as a string, bytes, dictionary, or list.

    Returns:
        The exact ETA canonical string ready for CAdES-BES SHA-256 hashing.
    """
    if isinstance(json_payload, (str, bytes)):
        # Strictly preserve string representation of all numbers to avoid float drift
        data = json.loads(json_payload, parse_float=str, parse_int=str)
    else:
        data = json_payload

    return _canonicalize_value(data)


def _canonicalize_value(val: Any) -> str:
    """
    Recursively canonicalize a JSON value according to ETA Canonical Serialization rules.
    """
    if isinstance(val, dict):
        parts: list[str] = []
        for k, v in val.items():
            upper_k = str(k).upper()
            key_token = f'"{upper_k}"'
            if isinstance(v, (list, tuple)):
                # Rule 4 (The Array Rule):
                # 1. Prefix the entire array with the uppercase array property name.
                parts.append(key_token)
                # 2. Before every array element inside it, additionally prepend the uppercase array property name.
                for item in v:
                    parts.append(key_token)
                    parts.append(_canonicalize_value(item))
            else:
                parts.append(key_token)
                parts.append(_canonicalize_value(v))
        return "".join(parts)

    elif isinstance(val, (list, tuple)):
        # Fallback for standalone array at root
        parts = []
        for item in val:
            parts.append(_canonicalize_value(item))
        return "".join(parts)

    elif isinstance(val, bool):
        # Rule 2: Booleans serialize as lowercase "true" or "false" in double quotes
        return '"true"' if val else '"false"'

    elif val is None:
        return '""'

    else:
        # Rule 2 & 3: Simple values (strings and exact numeric strings) enclosed in double quotes.
        # Exactly as written in the document without normalization.
        return f'"{str(val)}"'
