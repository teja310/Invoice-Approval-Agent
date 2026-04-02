from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, ValidationError

from schema import ApprovalResult, Invoice, PaymentResult, ValidationResult


class IngestionInput(BaseModel):
    invoice_path: str = Field(..., min_length=1)


class IngestionOutput(BaseModel):
    invoice: Invoice


class ValidationInput(BaseModel):
    invoice: Invoice
    db_path: str = Field(..., min_length=1)


class ValidationOutput(BaseModel):
    validation: ValidationResult


class ApprovalInput(BaseModel):
    invoice: Invoice
    validation: ValidationResult


class ApprovalOutput(BaseModel):
    approval: ApprovalResult


class PaymentInput(BaseModel):
    invoice: Invoice
    approval: ApprovalResult


class PaymentOutput(BaseModel):
    payment: PaymentResult


def validate_or_raise(model: type[BaseModel], payload):
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Schema validation failed for {model.__name__}: {exc}") from exc
