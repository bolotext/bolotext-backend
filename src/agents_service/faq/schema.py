from pydantic import BaseModel, ConfigDict, Field

from agents_service.core.partial import partial_model


class FAQPair(BaseModel):
    """One question the agent can recognize and its scripted answer."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "Can I pay in installments?",
                "answer": "Yes, please contact our branch to set up an installment plan.",
            }
        }
    )

    question: str = Field(..., description="A question the agent should be able to answer, in the caller's likely phrasing.")
    answer: str = Field(..., description="The answer the agent gives when it matches this question.")


class FAQSettings(BaseModel):
    enabled: bool = Field(False, description="Whether the agent draws on `pairs` to answer caller questions.")
    pairs: list[FAQPair] = Field([], description="Question/answer pairs the agent can use; replaced wholesale on update, not merged item-by-item.")


FAQSettingsUpdate = partial_model(FAQSettings)
