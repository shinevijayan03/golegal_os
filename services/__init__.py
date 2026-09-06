"""
GoLegal Services Package
"""
from services.validation import (
    validate_pan, validate_pincode, validate_email, validate_phone, mask_aadhaar, validate_commercial_terms
)
from services.rule_engine import calculate_stamp_duty, get_default_clauses
from services.stamping_service import StampingService, InsufficientStampingBalanceError
from services.esign_service import ESignService, AadhaarVerificationError, RateLimitLockoutError
from services.workflow_service import WorkflowService, InvalidStateTransitionError
from services.doc_assembly import DocumentAssemblyEngine, NumberedCanvas
from services.notification import NotificationService

__all__ = [
    "validate_pan",
    "validate_pincode",
    "validate_email",
    "validate_phone",
    "mask_aadhaar",
    "validate_commercial_terms",
    "calculate_stamp_duty",
    "get_default_clauses",
    "StampingService",
    "InsufficientStampingBalanceError",
    "ESignService",
    "AadhaarVerificationError",
    "RateLimitLockoutError",
    "WorkflowService",
    "InvalidStateTransitionError",
    "DocumentAssemblyEngine",
    "NumberedCanvas",
    "NotificationService",
]
