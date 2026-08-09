"""
app.modules.eta.services — ETA compliance services (Canonical Serialization, Crypto Hashing, Gateway, Signing, Document Builder, Submission Engine, Error Translation, Receipts, & Local PDF).
"""
from app.modules.eta.services.builder import build_eta_invoice, prepare_signed_eta_document
from app.modules.eta.services.canonical import serialize_document
from app.modules.eta.services.crypto import compute_cades_bes_hash, compute_cades_bes_hash_bytes
from app.modules.eta.services.gateway import EtaGateway, TokenBucket
from app.modules.eta.services.pdf import generate_local_invoice_pdf, generate_qr_code_image
from app.modules.eta.services.receipts import (
    build_and_sign_receipt_batch,
    prepare_eta_receipt,
    submit_receipt_batch,
)
from app.modules.eta.services.signing import (
    CloudHsmProvider,
    LocalHardwareTokenProvider,
    SigningProvider,
    get_signing_provider,
)
from app.modules.eta.services.submission import submit_eta_batch
from app.modules.eta.services.translation import (
    ETA_ERROR_DICTIONARY,
    process_document_status_event,
    register_eta_event_consumers,
    translate_eta_error,
    translate_eta_validation_errors,
)

__all__ = [
    "serialize_document",
    "compute_cades_bes_hash",
    "compute_cades_bes_hash_bytes",
    "EtaGateway",
    "TokenBucket",
    "SigningProvider",
    "CloudHsmProvider",
    "LocalHardwareTokenProvider",
    "get_signing_provider",
    "build_eta_invoice",
    "prepare_signed_eta_document",
    "submit_eta_batch",
    "ETA_ERROR_DICTIONARY",
    "translate_eta_error",
    "translate_eta_validation_errors",
    "process_document_status_event",
    "register_eta_event_consumers",
    "prepare_eta_receipt",
    "build_and_sign_receipt_batch",
    "submit_receipt_batch",
    "generate_local_invoice_pdf",
    "generate_qr_code_image",
]
