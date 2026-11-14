"""
GoLegal vNext Services Package.
"""
from golegal.services.auth_service import AuthService, TenantIsolationError
from golegal.services.catalog_service import CatalogService, LegalEligibilityError
from golegal.services.contract_service import (
    ContractService, ContractValidationError, StaleEtagError, SelfApprovalError
)
from golegal.services.document_service import DocumentService, FileValidationError
from golegal.services.provider_service import (
    ProviderService, WebhookVerificationError, ReplayWindowExpiredError
)
from golegal.services.stamping_service import StampingService, StampGateError
from golegal.services.reminder_service import ReminderService
from golegal.services.gpu_vision_service import GPUVisionService
from golegal.services.ai_insight_service import AIInsightService, AIDisabledError
from golegal.services.evidence_service import EvidenceService, TamperDetectedError

__all__ = [
    "AuthService", "TenantIsolationError",
    "CatalogService", "LegalEligibilityError",
    "ContractService", "ContractValidationError", "StaleEtagError", "SelfApprovalError",
    "DocumentService", "FileValidationError",
    "ProviderService", "WebhookVerificationError", "ReplayWindowExpiredError",
    "StampingService", "StampGateError",
    "ReminderService",
    "GPUVisionService",
    "AIInsightService", "AIDisabledError",
    "EvidenceService", "TamperDetectedError"
]
