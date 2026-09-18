from pydantic import BaseModel, ConfigDict

from agents_service.core.partial import partial_model


class FAQPair(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "Can I pay in installments?",
                "answer": "Yes, please contact our branch to set up an installment plan.",
            }
        }
    )

    question: str
    answer: str


class FAQSettings(BaseModel):
    enabled: bool = False
    pairs: list[FAQPair] = []


FAQSettingsUpdate = partial_model(FAQSettings)
