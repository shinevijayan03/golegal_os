"""
GoLegal Services Package
"""
from services.agreement_service import AgreementAccessError, AgreementService, demo_payload, empty_payload
from services.doc_assembly import DocumentAssemblyEngine, NumberedCanvas
from services.document_service import DocumentService
from services.esign_service import AadhaarVerificationError, ESignService, RateLimitLockoutError
from services.notification import NotificationService
from services.payment_service import PaymentError, PaymentService
from services.rule_engine import (
    AGREEMENT_TYPE_LABELS, OPTIONAL_TOGGLES, STATE_STAMP_RULES, calculate_stamp_duty, compute_fees,
    default_toggles, get_default_clauses, render_clauses_text,
)
from services.stamping_service import InsufficientStampingBalanceError, StampingService
from services.validation import (
    mask_aadhaar, safe_mask_aadhaar, validate_aadhaar, validate_commercial_terms, validate_email, validate_pan,
    validate_party, validate_phone, validate_pincode, validate_wizard_payload,
)
from services.workflow_service import InvalidStateTransitionError, WorkflowService

__all__ = [
    "validate_pan", "validate_pincode", "validate_email", "validate_phone", "validate_aadhaar", "mask_aadhaar",
    "safe_mask_aadhaar", "validate_commercial_terms", "validate_party", "validate_wizard_payload",
    "calculate_stamp_duty", "compute_fees", "get_default_clauses", "default_toggles", "render_clauses_text",
    "STATE_STAMP_RULES", "OPTIONAL_TOGGLES", "AGREEMENT_TYPE_LABELS",
    "StampingService", "InsufficientStampingBalanceError",
    "ESignService", "AadhaarVerificationError", "RateLimitLockoutError",
    "WorkflowService", "InvalidStateTransitionError",
    "DocumentAssemblyEngine", "NumberedCanvas", "DocumentService",
    "NotificationService", "PaymentService", "PaymentError",
    "AgreementService", "AgreementAccessError", "empty_payload", "demo_payload",
]
