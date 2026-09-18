from typing import Literal

from pydantic import BaseModel, ConfigDict

from agents_service.core.partial import partial_model


class ExtractionField(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "field_name": "payment_promised",
                "field_description": "Did the customer promise to pay?",
                "field_type": "boolean",
                "enum_values": None,
                "is_required": True,
            }
        }
    )

    field_name: str
    field_description: str
    field_type: Literal["string", "enum", "number", "boolean"]
    enum_values: list[str] | None = None
    is_required: bool = False


class AnalyticsSettings(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "disposition_enabled": True,
                "disposition_prompt": "Classify this call as one of: promise_to_pay, refused, unreachable.",
                "post_call_extraction_enabled": True,
                "extraction_fields": [
                    {
                        "field_name": "payment_promised",
                        "field_description": "Did the customer promise to pay?",
                        "field_type": "boolean",
                        "is_required": True,
                    }
                ],
            }
        }
    )

    disposition_enabled: bool = False
    disposition_prompt: str | None = None
    post_call_extraction_enabled: bool = False
    extraction_fields: list[ExtractionField] = []


AnalyticsSettingsUpdate = partial_model(AnalyticsSettings)
