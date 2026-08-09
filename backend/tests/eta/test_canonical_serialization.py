"""
tests/eta/test_canonical_serialization.py — Unit tests for ETA Canonical Serialization (FR-531)
and CAdES-BES Hashing (FR-532).

Verifies compliance with ETA's 5 Canonicalization Rules:
1. Uppercase Keys
2. Double Quotes on keys and simple values
3. Exact Numeric Values (preserving trailing zeros like "0.0", "150.50")
4. The Array Rule (prefix array name before array AND before every element)
5. Document insertion order
"""
from __future__ import annotations

import hashlib
import json
import pytest

from app.modules.eta.services.canonical import serialize_document
from app.modules.eta.services.crypto import compute_cades_bes_hash, compute_cades_bes_hash_bytes


def test_eta_array_rule_reference():
    """
    Test Rule 4 (The Array Rule) against the ETA specification reference vector:
    In JSON, the entire array serialization is prefixed with the UPPERCASE array property name,
    AND every array element inside it is additionally preceded by that same UPPERCASE array property name.
    """
    json_payload = '{"invoiceLines": [{"element": 1}, {"element": 2}]}'
    canonical = serialize_document(json_payload)

    expected = '"INVOICELINES""INVOICELINES""ELEMENT""1""INVOICELINES""ELEMENT""2"'
    assert canonical == expected, (
        f"Array rule failed.\nExpected: {expected}\nGot:      {canonical}"
    )


def test_numeric_string_preservation_no_float_normalization():
    """
    Test Rule 3 (Exact Values):
    Property values are taken exactly as they appear. 0.0 must serialize as "0.0",
    not "0" or "0.00". 150.50 must serialize as "150.50", not "150.5".
    """
    json_payload = '''
    {
        "rate": 0.0,
        "taxAmount": 0.00,
        "unitPrice": 150.50,
        "quantity": 10.0000,
        "discount": 0
    }
    '''
    canonical = serialize_document(json_payload)

    assert '"RATE""0.0"' in canonical
    assert '"TAXAMOUNT""0.00"' in canonical
    assert '"UNITPRICE""150.50"' in canonical
    assert '"QUANTITY""10.0000"' in canonical
    assert '"DISCOUNT""0"' in canonical

    expected_full = (
        '"RATE""0.0"'
        '"TAXAMOUNT""0.00"'
        '"UNITPRICE""150.50"'
        '"QUANTITY""10.0000"'
        '"DISCOUNT""0"'
    )
    assert canonical == expected_full


def test_complex_nested_invoice_payload_canonicalization():
    """
    Test a tricky Egyptian Tax Authority e-Invoice JSON payload including:
      - Root metadata
      - Nested seller and buyer objects
      - Array of invoice lines, where each line contains a nested array of taxableItems
      - Decimals ("0.0", "150.50", "14.00")
      - Booleans and null values
    """
    invoice_payload = '''
    {
        "documentType": "I",
        "documentTypeVersion": "1.0",
        "dateTimeIssued": "2026-07-31T00:00:00Z",
        "taxpayerActivityCode": "4610",
        "seller": {
            "rin": "123456789",
            "companyTradeName": "OmniERP Test Merchant",
            "branchCode": "0",
            "address": {
                "branchID": "0",
                "country": "EG",
                "governorate": "Cairo",
                "regionCity": "Maadi"
            }
        },
        "buyer": {
            "type": "B",
            "id": "987654321",
            "name": "Acme Corp"
        },
        "invoiceLines": [
            {
                "description": "Enterprise Licensing",
                "itemType": "EGS",
                "itemCode": "EG-123456789-SKU1",
                "unitType": "EA",
                "quantity": 2.00,
                "unitValue": 150.50,
                "salesTotal": 301.00,
                "total": 343.14,
                "valueDifference": 0.0,
                "taxableItems": [
                    {
                        "taxType": "T1",
                        "amount": 42.14,
                        "subType": "V009",
                        "rate": 14.0
                    },
                    {
                        "taxType": "T2",
                        "amount": 0.0,
                        "subType": "Tbl01",
                        "rate": 0.0
                    }
                ]
            }
        ],
        "totalDiscountAmount": 0.0,
        "totalSalesAmount": 301.00,
        "netAmount": 301.00,
        "taxTotals": [
            {
                "taxType": "T1",
                "amount": 42.14
            }
        ],
        "totalAmount": 343.14,
        "extraDiscountAmount": 0.00,
        "totalItemsDiscountAmount": 0.0
    }
    '''
    canonical = serialize_document(invoice_payload)

    # 1. Check UPPERCASE keys
    assert '"DOCUMENTTYPE""I"' in canonical
    assert '"DOCUMENTTYPEVERSION""1.0"' in canonical
    assert '"SELLER"' in canonical
    assert '"BUYER"' in canonical

    # 2. Check nested object
    assert '"SELLER""RIN""123456789""COMPANYTRADENAME""OmniERP Test Merchant"' in canonical
    assert '"ADDRESS""BRANCHID""0""COUNTRY""EG"' in canonical

    # 3. Check Level-1 array rule (INVOICELINES)
    assert '"INVOICELINES""INVOICELINES""DESCRIPTION""Enterprise Licensing"' in canonical

    # 4. Check Level-2 nested array rule inside invoice line (TAXABLEITEMS)
    assert (
        '"TAXABLEITEMS""TAXABLEITEMS""TAXTYPE""T1""AMOUNT""42.14""SUBTYPE""V009""RATE""14.0"'
        '"TAXABLEITEMS""TAXTYPE""T2""AMOUNT""0.0""SUBTYPE""Tbl01""RATE""0.0"'
    ) in canonical

    # 5. Check exact float strings
    assert '"QUANTITY""2.00"' in canonical
    assert '"UNITVALUE""150.50"' in canonical
    assert '"VALUEDIFFERENCE""0.0"' in canonical
    assert '"EXTRADISCOUNTAMOUNT""0.00"' in canonical


def test_cades_bes_sha256_hashing_consistency():
    """
    Test SHA-256 calculation over canonical ETA string (FR-532).
    """
    sample_json = '{"invoiceLines": [{"element": 1}, {"element": 2}]}'
    canonical = serialize_document(sample_json)

    # Compute hash via module service
    digest_hex = compute_cades_bes_hash(canonical)
    digest_bytes = compute_cades_bes_hash_bytes(canonical)

    # Manual verification against standard Python hashlib
    expected_bytes = hashlib.sha256(canonical.encode("utf-8")).digest()
    expected_hex = expected_bytes.hex()

    assert digest_hex == expected_hex
    assert digest_bytes == expected_bytes
    assert len(digest_hex) == 64
    assert digest_hex == "34dfb829c92d4e944113e070b549a315cb1167ef3eeedef729b4dc2e6dbd0390"


def test_primitive_types_and_edge_cases():
    """
    Test booleans, nulls, empty strings, and empty arrays.
    """
    payload = '''
    {
        "activeFlag": true,
        "testFlag": false,
        "optionalField": null,
        "emptyString": "",
        "emptyArray": []
    }
    '''
    canonical = serialize_document(payload)
    expected = (
        '"ACTIVEFLAG""true"'
        '"TESTFLAG""false"'
        '"OPTIONALFIELD"""'
        '"EMPTYSTRING"""'
        '"EMPTYARRAY"'
    )
    assert canonical == expected
