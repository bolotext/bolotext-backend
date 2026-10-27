import re

import pytest
from common.enums import Role

from agents_service.agent_templates.data import TEMPLATES
from tests.factories import code, data, error_type, set_auth

pytestmark = pytest.mark.asyncio

_VAR = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")


async def test_list_and_get_templates(client):
    set_auth(client.app, "user-1", "org-1")
    resp = await client.get("/api/v1/agent-templates")
    assert code(resp) == 200
    keys = {t["key"] for t in data(resp)}
    assert {"appointment-booking", "insurance-policy-renewal", "loan-enquiry"} <= keys
    assert len(keys) == 5

    detail = data(await client.get("/api/v1/agent-templates/loan-enquiry"))
    assert detail["system_prompt"]
    assert detail["regulatory_notes"]
    assert "disclaimer" in detail


async def test_unknown_template_is_404(client):
    set_auth(client.app, "user-1", "org-1")
    resp = await client.get("/api/v1/agent-templates/nope")
    assert code(resp) == 404
    assert error_type(resp) == "NOT_FOUND"


async def test_create_agent_from_template_prefills_config(client):
    set_auth(client.app, "user-1", "org-1")
    resp = await client.post("/api/v1/agent-templates/appointment-booking/create-agent", json={"name": "My Clinic Bot"})
    assert code(resp) == 201
    agent = data(resp)
    assert agent["agent_details"]["name"] == "My Clinic Bot"
    assert agent["prompt"]["system_prompt"]
    assert agent["prompt"]["pre_call_variables"]["company_name"]
    assert agent["faq"]["enabled"] is True and agent["faq"]["pairs"]
    assert agent["languages"] == ["en-IN", "hi-IN"]


async def test_create_from_template_defaults_name_and_rejects_qa(client):
    set_auth(client.app, "user-1", "org-1")
    resp = await client.post("/api/v1/agent-templates/emi-payment-reminder/create-agent")
    assert data(resp)["agent_details"]["name"] == TEMPLATES["emi-payment-reminder"].name

    set_auth(client.app, "qa-1", "org-1", Role.QA)
    denied = await client.post("/api/v1/agent-templates/emi-payment-reminder/create-agent")
    assert code(denied) == 403


def test_every_template_discloses_ai_and_declares_its_variables():
    for t in TEMPLATES.values():
        assert "AI" in t.welcome_message, t.key
        assert "AI voice assistant" in t.system_prompt, t.key
        assert t.regulatory_notes, t.key
        used = set(_VAR.findall(" ".join([t.welcome_message, t.system_prompt, t.ending_message])))
        used |= set(_VAR.findall(" ".join(p.answer for p in t.faq)))
        assert used <= set(t.pre_call_variables), (t.key, used - set(t.pre_call_variables))
