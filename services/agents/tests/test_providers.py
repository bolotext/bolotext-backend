import pytest

from tests.factories import code, data, set_auth

pytestmark = pytest.mark.asyncio


async def test_combined_provider_catalog_has_all_three_kinds(client):
    set_auth(client.app, "user-1", "org-1")
    resp = await client.get("/api/v1/providers")
    assert code(resp) == 200
    body = data(resp)
    assert {"llm", "stt", "tts"} <= body.keys()
    assert any(p["provider_id"] == "openai" for p in body["llm"])
    assert any(p["provider_id"] == "gnani" for p in body["stt"])
    assert any(p["provider_id"] == "elevenlabs" for p in body["tts"])


async def test_individual_provider_endpoints(client):
    set_auth(client.app, "user-1", "org-1")
    llm_resp = await client.get("/api/v1/providers/llm")
    stt_resp = await client.get("/api/v1/providers/stt")
    tts_resp = await client.get("/api/v1/providers/tts")

    assert code(llm_resp) == 200
    assert code(stt_resp) == 200
    assert code(tts_resp) == 200
    assert {p["provider_id"] for p in data(llm_resp)} == {"openai", "groq", "gnani"}
    assert {p["provider_id"] for p in data(stt_resp)} == {"gnani", "elevenlabs", "microsoft"}
