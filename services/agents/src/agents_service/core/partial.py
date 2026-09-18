"""Generates a "partial" version of a section model: every field becomes
optional with a default of None, so a PATCH payload can supply just the
fields it wants to change (see agents/router.py and agents/service.py, which
merge the supplied fields onto the existing section with `exclude_unset`).
"""

from pydantic import BaseModel, create_model
from pydantic.fields import FieldInfo


def partial_model(model: type[BaseModel], name: str | None = None) -> type[BaseModel]:
    fields: dict[str, tuple[object, FieldInfo]] = {}
    for field_name, field in model.model_fields.items():
        annotation = field.annotation if field.annotation is type(None) else (field.annotation | None)
        fields[field_name] = (annotation, FieldInfo.merge_field_infos(field, default=None))

    return create_model(name or f"{model.__name__}Update", __base__=BaseModel, **fields)
