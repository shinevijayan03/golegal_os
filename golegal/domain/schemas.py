"""
Pydantic v2 Validation Schemas & Error Envelopes for GoLegal vNext.
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List, Generic, TypeVar
from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class APIResponse(BaseModel, Generic[T]):
    data: Optional[T] = None
    error: Optional[ErrorDetail] = None
    request_id: str
    etag_version: Optional[int] = None


class ContractCreateSchema(BaseModel):
    template_version_id: str
    title: str = Field(min_length=3, max_length=255)
    field_values: Dict[str, Any] = Field(default_factory=dict)


class ContractUpdateFieldsSchema(BaseModel):
    expected_etag_version: int
    field_values: Dict[str, Any]


class ReviewDecisionSchema(BaseModel):
    revision_id: str
    decision: str  # approve, reject
    comment: Optional[str] = None


class SignRequestSchema(BaseModel):
    revision_id: str
    mode: str = "mock"
    provider: str = "mock_esign"
