"""Backward-compatible names for the former SECUI-only knowledge service."""

from app.services.store_schema_knowledge import StoreSchemaKnowledge, StoreSchemaMatch

SecuiKnowledge = StoreSchemaKnowledge
SecuiMatch = StoreSchemaMatch

__all__ = ["SecuiKnowledge", "SecuiMatch"]
