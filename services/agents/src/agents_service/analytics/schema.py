from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agents_service.core.partial import partial_model
from agents_service.post_call_trigger.schema import PostCallTriggerSettings


class ExtractionField(BaseModel):
    """One structured data point the LLM should extract from the call
    transcript after it ends (e.g. for CRM sync or compliance review)."""

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

    field_name: str = Field(..., description="Key this field is reported under in the extraction result.")
    field_description: str = Field(..., description="Explains to the LLM what to extract for this field.")
    field_type: Literal["string", "enum", "number", "boolean"] = Field(..., description="Expected JSON type of the extracted value.")
    enum_values: list[str] | None = Field(None, description="Allowed values when `field_type` is `\"enum\"`; ignored otherwise.")
    is_required: bool = Field(False, description="Whether extraction should be flagged as incomplete if this field can't be determined from the call.")


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
                "post_call_trigger": {
                    "post_call_trigger_enabled": True,
                    "method": "POST",
                    "url": "https://example.com/webhooks/call-ended",
                    "headers": {"Authorization": "Bearer xxx"},
                },
            }
        }
    )

    disposition_enabled: bool = Field(False, description="Whether the LLM should classify each ended call into a disposition category.")
    disposition_prompt: str | None = Field(None, description="Instructions telling the LLM which disposition categories to choose between and how.")
    post_call_extraction_enabled: bool = Field(False, description="Whether to run structured data extraction (`extraction_fields`) after each call.")
    extraction_fields: list[ExtractionField] = Field([], description="Structured data points to extract from the call transcript when extraction is enabled.")
    # A webhook the platform calls once a call ends — see
    # post_call_trigger/schema.py's docstring. Has its own
    # POST/GET/PATCH /agents/{id}/post-call-trigger routes (see
    # agents_service.post_call_trigger.router) alongside the generic
    # PATCH /agents/{id}/analytics this section already gets.
    post_call_trigger: PostCallTriggerSettings = Field(
        default=PostCallTriggerSettings(),
        description="Webhook fired once a call ends; can also be managed via its own /agents/{agent_id}/post-call-trigger routes.",
    )


AnalyticsSettingsUpdate = partial_model(AnalyticsSettings)
