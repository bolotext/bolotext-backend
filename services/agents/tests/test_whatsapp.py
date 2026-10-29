from datetime import datetime
import asyncio

import pytest
from common.enums import Role

from agents_service.core.config import get_settings
from agents_service.whatsapp import crypto
from agents_service.whatsapp import service as wa_service
from agents_service.whatsapp.service import normalize_phone, parse_csv
from agents_service.whatsapp.model import WhatsAppContact, WhatsAppMessageEvent, WhatsAppSettings, WhatsAppTemplate
from agents_service.whatsapp.twilio_client import compute_signature
from tests.factories import code, data, error_type, set_auth

pytestmark = pytest.mark.asyncio

CSV = "customer_name,phone_number,message\nAsha,9876543210,Hi Asha\nRavi,+14155550100,Hello Ravi\nBad,12,x\nAsha2,98765 43210,dup\n,9876500000,no name\n"


@pytest.fixture(autouse=True)
def _fast_sends(monkeypatch):
    # No saved settings = simulated sending, so the suite never touches Twilio.
    monkeypatch.setattr(get_settings(), "whatsapp_send_delay_ms", 0)


async def _agent(client, name="Reminders"):
    resp = await client.post("/api/v1/whatsapp/agents", json={"name": name, "use_case": "payment-reminder"})
    assert code(resp) == 201
    return data(resp)["id"]


async def _upload(client, agent_id, csv_text=CSV, consent=True):
    return await client.post(
        f"/api/v1/whatsapp/agents/{agent_id}/contacts/upload",
        json={"filename": "c.csv", "csv": csv_text, "consent_confirmed": consent},
    )


async def _drain():
    await asyncio.gather(*list(wa_service._jobs))


async def test_normalize_phone():
    assert normalize_phone("98765 43210") == "+919876543210"
    assert normalize_phone("0098765432100") == "+98765432100"
    assert normalize_phone("+1 (415) 555-0100") == "+14155550100"
    for bad in ("12", "abc", "+0123456789", ""):
        with pytest.raises(ValueError):
            normalize_phone(bad)


async def test_parse_csv_reports_row_errors():
    valid, errors, total = parse_csv(CSV)
    assert [v["phone_number"] for v in valid] == [919876543210, 14155550100]
    assert total == 5 and {e.row for e in errors} == {4, 5, 6}


async def test_agent_crud_and_org_isolation(client):
    set_auth(client.app, "u1", "org-1")
    agent_id = await _agent(client)
    patch = await client.patch(f"/api/v1/whatsapp/agents/{agent_id}", json={"name": "Renamed", "twilio_sender": "98765 43210"})
    assert data(patch)["name"] == "Renamed" and data(patch)["twilio_sender"] == "+919876543210"
    assert len(data(await client.get("/api/v1/whatsapp/agents"))) == 1

    set_auth(client.app, "u2", "org-2")
    assert error_type(await client.get(f"/api/v1/whatsapp/agents/{agent_id}")) == "NOT_FOUND"
    assert data(await client.get("/api/v1/whatsapp/agents")) == []

    set_auth(client.app, "u1", "org-1")
    assert code(await client.delete(f"/api/v1/whatsapp/agents/{agent_id}")) == 200
    assert error_type(await client.get(f"/api/v1/whatsapp/agents/{agent_id}")) == "NOT_FOUND"


async def test_qa_is_read_only(client):
    set_auth(client.app, "qa", "org-1", Role.QA)
    assert error_type(await client.post("/api/v1/whatsapp/agents", json={"name": "x"})) == "FORBIDDEN"
    set_auth(client.app, "u1", "org-1")
    agent_id = await _agent(client)
    set_auth(client.app, "qa", "org-1", Role.QA)
    assert code(await client.get(f"/api/v1/whatsapp/agents/{agent_id}")) == 200
    assert error_type(await _upload(client, agent_id)) == "FORBIDDEN"


async def test_csv_upload_and_contact_crud(client):
    set_auth(client.app, "u1", "org-1")
    agent_id = await _agent(client)
    assert error_type(await _upload(client, agent_id, consent=False)) == "UNPROCESSABLE_ENTITY"
    assert error_type(await _upload(client, agent_id, "name,phone\na,b")) == "UNPROCESSABLE_ENTITY"

    res = data(await _upload(client, agent_id))
    assert res["batch"]["valid_rows"] == 2 and res["batch"]["invalid_rows"] == 3 and len(res["errors"]) == 3

    listing = data(await client.get(f"/api/v1/whatsapp/agents/{agent_id}/contacts", params={"q": "asha"}))
    assert listing["total"] == 1 and listing["items"][0]["phone_number"] == 919876543210

    contact_id = listing["items"][0]["id"]
    upd = await client.patch(f"/api/v1/whatsapp/agents/{agent_id}/contacts/{contact_id}", json={"message": "New text"})
    assert data(upd)["message"] == "New text"
    bad = await client.patch(f"/api/v1/whatsapp/agents/{agent_id}/contacts/{contact_id}", json={"phone_number": "123"})
    assert error_type(bad) == "UNPROCESSABLE_ENTITY"

    added = await client.post(f"/api/v1/whatsapp/agents/{agent_id}/contacts", json={"customer_name": "Zed", "phone_number": "9000000001", "message": "m"})
    assert code(added) == 201
    dup = await client.post(f"/api/v1/whatsapp/agents/{agent_id}/contacts", json={"customer_name": "Zed", "phone_number": "9000000001", "message": "m"})
    assert error_type(dup) == "CONFLICT"

    assert data(await client.delete(f"/api/v1/whatsapp/agents/{agent_id}/contacts/{contact_id}")) is None
    all_ids = [c["id"] for c in data(await client.get(f"/api/v1/whatsapp/agents/{agent_id}/contacts"))["items"]]
    bulk = await client.post(f"/api/v1/whatsapp/agents/{agent_id}/contacts/bulk-delete", json={"contact_ids": all_ids})
    assert data(bulk) == 2
    assert data(await client.get(f"/api/v1/whatsapp/agents/{agent_id}/stats"))["total"] == 0


async def test_template_lifecycle(client):
    set_auth(client.app, "u1", "org-1")
    agent_id = await _agent(client)
    base = f"/api/v1/whatsapp/agents/{agent_id}/templates"
    bad = await client.post(base, json={"name": "t", "body": "Hi {{nope}}"})
    assert error_type(bad) == "UNPROCESSABLE_ENTITY"

    t = data(await client.post(base, json={"name": "Reminder", "body": "Hi {{customer_name}}, {{message}}"}))
    assert t["approval_status"] == "draft" and t["variables"] == ["customer_name", "message"]
    assert error_type(await client.post(base, json={"name": "Reminder", "body": "x"})) == "CONFLICT"

    sub = data(await client.post(f"{base}/{t['id']}/submit"))
    assert sub["approval_status"] == "pending" and sub["twilio_content_sid"]
    assert error_type(await client.patch(f"{base}/{t['id']}", json={"body": "new"})) == "CONFLICT"
    assert error_type(await client.post(f"{base}/{t['id']}/submit")) == "CONFLICT"

    synced = data(await client.post(f"{base}/{t['id']}/sync-status"))  # dry-run auto-approves
    assert synced["approval_status"] == "approved"


async def test_send_free_text_is_idempotent(client):
    set_auth(client.app, "u1", "org-1")
    agent_id = await _agent(client)
    batch_id = data(await _upload(client, agent_id))["batch"]["id"]
    send_url = f"/api/v1/whatsapp/agents/{agent_id}/send"

    assert error_type(await client.post(send_url, json={"batch_id": batch_id})) == "UNPROCESSABLE_ENTITY"  # no consent
    assert error_type(await client.post(send_url, json={"consent_confirmed": True})) == "BAD_REQUEST"

    res = data(await client.post(send_url, json={"batch_id": batch_id, "consent_confirmed": True}))
    assert res["queued"] == 2 and res["dry_run"] is True
    await _drain()
    stats = data(await client.get(f"/api/v1/whatsapp/agents/{agent_id}/stats"))
    assert stats["sent"] == 2 and stats["pending"] == 0

    again = data(await client.post(send_url, json={"batch_id": batch_id, "consent_confirmed": True}))
    assert again["queued"] == 0 and again["skipped"] == 2  # never double-send


async def test_send_selected_with_template_and_opt_out(client):
    set_auth(client.app, "u1", "org-1")
    agent_id = await _agent(client)
    await _upload(client, agent_id)
    items = data(await client.get(f"/api/v1/whatsapp/agents/{agent_id}/contacts"))["items"]
    first, second = items[0]["id"], items[1]["id"]
    await client.patch(f"/api/v1/whatsapp/agents/{agent_id}/contacts/{second}", json={"opted_out": True})

    tpl_base = f"/api/v1/whatsapp/agents/{agent_id}/templates"
    t = data(await client.post(tpl_base, json={"name": "T", "body": "Hi {{customer_name}}"}))
    send_url = f"/api/v1/whatsapp/agents/{agent_id}/send"
    body = {"contact_ids": [first, second], "template_id": t["id"], "consent_confirmed": True}
    assert error_type(await client.post(send_url, json=body)) == "UNPROCESSABLE_ENTITY"  # not approved

    await client.post(f"{tpl_base}/{t['id']}/submit")
    await client.post(f"{tpl_base}/{t['id']}/sync-status")
    res = data(await client.post(send_url, json=body))
    assert res["queued"] == 1 and res["skipped"] == 1
    await _drain()
    sent = data(await client.get(f"/api/v1/whatsapp/agents/{agent_id}/contacts", params={"status": "sent"}))
    assert sent["total"] == 1 and sent["items"][0]["id"] == first and sent["items"][0]["twilio_message_sid"].startswith("DRY")


async def test_status_callback_updates_and_never_regresses(client):
    set_auth(client.app, "u1", "org-1")
    agent_id = await _agent(client)
    batch_id = data(await _upload(client, agent_id))["batch"]["id"]
    await client.post(f"/api/v1/whatsapp/agents/{agent_id}/send", json={"batch_id": batch_id, "consent_confirmed": True})
    await _drain()
    sid = data(await client.get(f"/api/v1/whatsapp/agents/{agent_id}/contacts"))["items"][0]["twilio_message_sid"]

    async def callback(status, extra=""):
        return await client.post(
            "/api/v1/whatsapp/twilio/status-callback",
            content=f"MessageSid={sid}&MessageStatus={status}{extra}",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    async def status_of(sid_):
        items = data(await client.get(f"/api/v1/whatsapp/agents/{agent_id}/contacts"))["items"]
        return next(c for c in items if c["twilio_message_sid"] == sid_)

    assert code(await callback("delivered")) == 200
    assert (await status_of(sid))["send_status"] == "delivered"
    await callback("sent")  # late, out-of-order
    assert (await status_of(sid))["send_status"] == "delivered"
    await callback("failed", "&ErrorCode=63016")
    failed = await status_of(sid)
    assert failed["send_status"] == "failed" and "63016" in failed["error"]


async def test_message_status_tab_stores_every_event_with_full_payload(client):
    set_auth(client.app, "u1", "org-1")
    agent_id = await _agent(client)
    batch_id = data(await _upload(client, agent_id))["batch"]["id"]
    await client.post(f"/api/v1/whatsapp/agents/{agent_id}/send", json={"batch_id": batch_id, "consent_confirmed": True})
    await _drain()
    base = f"/api/v1/whatsapp/agents/{agent_id}/messages"
    first = data(await client.get(base))["items"][0]
    assert first["status"] == "simulated" and first["events"] == 1
    sid = first["message_sid"]

    async def callback(status, extra=""):
        await client.post(
            "/api/v1/whatsapp/twilio/status-callback",
            content=f"MessageSid={sid}&MessageStatus={status}&To=whatsapp%3A%2B91987{extra}",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    await callback("delivered")
    await callback("sent")  # late: logged, but the latest status stays "delivered"
    row = data(await client.get(base, params={"status": "delivered"}))["items"][0]
    assert row["status"] == "delivered" and row["events"] == 3
    assert data(await client.get(base, params={"status": "failed"}))["total"] == 0
    await callback("undelivered", "&ErrorCode=63016&ErrorMessage=Template%20not%20approved")
    events = data(await client.get(f"{base}/{row['contact_id']}/events"))
    assert [e["status"] for e in events] == ["simulated", "delivered", "sent", "undelivered"]
    assert events[-1]["error_code"] == "63016" and events[-1]["payload"]["To"].startswith("whatsapp:")
    assert data(await client.get(base))["items"][0]["status"] == "undelivered"
    # Other orgs can't read them; deleting the contact removes its events.
    set_auth(client.app, "u2", "org-2")
    assert error_type(await client.get(f"{base}/{row['contact_id']}/events")) == "NOT_FOUND"
    set_auth(client.app, "u1", "org-1")
    await client.delete(f"/api/v1/whatsapp/agents/{agent_id}/contacts/{row['contact_id']}")
    assert await WhatsAppMessageEvent.find({"contact_id": row["contact_id"]}).count() == 0


async def test_field_mapper_types_custom_columns_and_template_placeholders(client):
    set_auth(client.app, "u1", "org-1")
    agent_id = await _agent(client)
    base = f"/api/v1/whatsapp/agents/{agent_id}"
    out = data(await client.get(base))
    assert [(f["key"], f["locked"]) for f in out["field_mapper"]] == [("full_name", True), ("phone_number", True)]
    assert [f["type"] for f in out["field_mapper"]] == ["string", "long"]

    for bad in ("Amount", "message", "phone_number", "1abc"):
        r = await client.put(f"{base}/field-mapper", json={"fields": [{"key": bad}]})
        assert error_type(r) == "UNPROCESSABLE_ENTITY", bad
    dup = await client.put(f"{base}/field-mapper", json={"fields": [{"key": "a"}, {"key": "a"}]})
    assert error_type(dup) == "UNPROCESSABLE_ENTITY"
    ok = await client.put(
        f"{base}/field-mapper",
        json={"fields": [{"key": "amount", "type": "number", "required": True}, {"key": "due", "type": "date"}, {"key": "vip", "type": "boolean"}]},
    )
    assert [f["key"] for f in data(ok)["field_mapper"]] == ["full_name", "phone_number", "amount", "due", "vip"]

    csv_text = "full_name,phone_number,amount,due,vip\nAsha,9876543210,1500.50,2026-11-05,yes\nRavi,9123456780,abc,,\nMina,9000000001,,,\n"
    res = data(await _upload(client, agent_id, csv_text))
    assert res["batch"]["valid_rows"] == 1 and len(res["errors"]) == 2
    contact = data(await client.get(f"{base}/contacts"))["items"][0]
    assert contact["customer_name"] == "Asha" and contact["data"]["amount"] == 1500.5
    assert contact["data"]["vip"] is True and contact["data"]["due"].startswith("2026-11-05")
    stored = await WhatsAppContact.get(contact["id"])
    assert isinstance(stored.data["due"], datetime) and isinstance(stored.data["amount"], float)

    # Custom keys are usable as template placeholders; unknown ones are rejected.
    t = await client.post(f"{base}/templates", json={"name": "due", "body": "Hi {{full_name}}, Rs {{amount}} due {{due}}"})
    assert data(t)["variables"] == ["full_name", "amount", "due"]
    bad_t = await client.post(f"{base}/templates", json={"name": "x", "body": "Hi {{nope}}"})
    assert error_type(bad_t) == "UNPROCESSABLE_ENTITY"

    # Manual contacts are validated against the mapper too.
    r = await client.post(f"{base}/contacts", json={"customer_name": "B", "phone_number": "9111111111", "data": {"amount": "x"}})
    assert error_type(r) == "UNPROCESSABLE_ENTITY"
    r = await client.post(f"{base}/contacts", json={"customer_name": "B", "phone_number": "9111111111", "data": {"amount": "20"}})
    assert code(r) == 201 and data(r)["data"] == {"amount": 20}


async def test_phone_number_is_stored_as_a_long_and_searchable(client):
    set_auth(client.app, "u1", "org-1")
    agent_id = await _agent(client)
    base = f"/api/v1/whatsapp/agents/{agent_id}"
    await _upload(client, agent_id, "full_name,phone_number\nAsha,98765 43210\nRavi,+14155550100\n")
    docs = await WhatsAppContact.get_pymongo_collection().find({}).to_list(10)
    assert sorted(d["phone_number"] for d in docs) == [14155550100, 919876543210]
    assert all(isinstance(d["phone_number"], int) for d in docs)
    # A plain JSON integer is accepted as input too.
    r = await client.post(f"{base}/contacts", json={"customer_name": "Zed", "phone_number": 919000000001})
    assert code(r) == 201 and data(r)["phone_number"] == 919000000001
    for q, n in (("98765", 1), ("+91 9876", 1), ("919876543210", 1), ("1415", 1), ("919", 2), ("55501", 0), ("Asha", 1)):
        got = data(await client.get(f"{base}/contacts", params={"q": q}))["total"]
        assert got == n, (q, got)


async def test_legacy_string_phone_numbers_are_migrated():
    from agents_service.db.mongodb import _migrate_phone_numbers

    coll = WhatsAppContact.get_pymongo_collection()
    await coll.insert_one({"whatsapp_agent_id": "a", "customer_name": "Old", "phone_number": "+919876543210", "message": ""})
    await _migrate_phone_numbers()
    assert (await coll.find_one({"customer_name": "Old"}))["phone_number"] == 919876543210


async def test_dry_run_template_is_reset_for_real_sending_and_sends_no_empty_variables(client, monkeypatch):
    set_auth(client.app, "admin", "org-1")
    agent_id = await _agent(client)
    base = f"/api/v1/whatsapp/agents/{agent_id}"
    await _upload(client, agent_id)
    # Created + "approved" while dry-run: the Content SID is a fake HXDRY… one.
    t = data(await client.post(f"{base}/templates", json={"name": "plain", "body": "hi how are you?"}))
    await client.post(f"{base}/templates/{t['id']}/submit")
    synced = data(await client.post(f"{base}/templates/{t['id']}/sync-status"))
    assert synced["approval_status"] == "approved" and synced["twilio_content_sid"].startswith("HXDRY")

    await client.put("/api/v1/whatsapp/settings", json={"twilio_account_sid": SID, "auth_token": TOKEN, "twilio_whatsapp_from": "+14155238886", "dry_run": False})
    listed = data(await client.get(f"{base}/templates"))[0]
    assert listed["approval_status"] == "draft" and listed["twilio_content_sid"] is None
    res = await client.post(f"{base}/send", json={"batch_id": data(await client.get(f"{base}/batches"))[0]["id"], "template_id": t["id"], "consent_confirmed": True})
    assert error_type(res) == "UNPROCESSABLE_ENTITY"

    # A real (approved) template without placeholders sends no ContentVariables.
    posted = []

    async def fake_request(self, method, url, **kwargs):
        posted.append(kwargs.get("data"))
        return {"sid": "SM1"}

    monkeypatch.setattr("agents_service.whatsapp.twilio_client.TwilioClient._request", fake_request)
    await WhatsAppTemplate.find_one(WhatsAppTemplate.whatsapp_agent_id == agent_id).update(
        {"$set": {"twilio_content_sid": "HXreal", "approval_status": "approved"}}
    )
    batch_id = data(await client.get(f"{base}/batches"))[0]["id"]
    assert code(await client.post(f"{base}/send", json={"batch_id": batch_id, "template_id": t["id"], "consent_confirmed": True})) == 202
    await _drain()
    assert posted and all(p["ContentSid"] == "HXreal" and "ContentVariables" not in p for p in posted)


async def test_templates_linked_from_twilio(client, monkeypatch):
    set_auth(client.app, "admin", "org-1")
    agent_id = await _agent(client)
    base = f"/api/v1/whatsapp/agents/{agent_id}"
    await _upload(client, agent_id)
    live = data(await client.get(f"{base}/twilio-templates"))
    appt = next(t for t in live if t["name"] == "sample_appointment")
    assert appt["variables"] == ["1", "2"] and appt["template_id"] is None

    r = await client.post(f"{base}/templates/import", json={"content_sid": appt["sid"], "mapping": {"1": "message"}})
    assert error_type(r) == "UNPROCESSABLE_ENTITY"  # variable 2 unmapped
    r = await client.post(f"{base}/templates/import", json={"content_sid": appt["sid"], "mapping": {"1": "message", "2": "nope"}})
    assert error_type(r) == "UNPROCESSABLE_ENTITY"
    r = await client.post(f"{base}/templates/import", json={"content_sid": "HXnothere", "mapping": {}})
    assert error_type(r) == "NOT_FOUND"
    ok = data(await client.post(f"{base}/templates/import", json={"content_sid": appt["sid"], "mapping": {"1": "message", "2": "full_name"}}))
    assert ok["source"] == "twilio" and ok["approval_status"] == "approved" and ok["var_names"] == ["1", "2"]
    assert ok["variables"] == ["message", "full_name"]
    assert error_type(await client.post(f"{base}/templates/import", json={"content_sid": appt["sid"], "mapping": {"1": "message", "2": "full_name"}})) == "CONFLICT"
    assert next(t for t in data(await client.get(f"{base}/twilio-templates")) if t["sid"] == appt["sid"])["template_id"] == ok["id"]

    # Managed in Twilio: no edit / submit here.
    assert error_type(await client.patch(f"{base}/templates/{ok['id']}", json={"name": "x"})) == "CONFLICT"
    assert error_type(await client.post(f"{base}/templates/{ok['id']}/submit")) == "CONFLICT"

    # An unsubmitted Twilio template is still sendable; variables go out under Twilio's own names.
    unsub = next(t for t in live if t["name"] == "sample_greeting")
    g = data(await client.post(f"{base}/templates/import", json={"content_sid": unsub["sid"], "mapping": {"1": "full_name"}}))
    assert g["approval_status"] == "draft"
    posted = []

    async def fake_send(self, **kwargs):
        posted.append(kwargs)
        return "DRYx"

    monkeypatch.setattr("agents_service.whatsapp.twilio_client.TwilioClient.send_message", fake_send)
    batch_id = data(await client.get(f"{base}/batches"))[0]["id"]
    for tid in (ok["id"], g["id"]):
        assert code(await client.post(f"{base}/send", json={"batch_id": batch_id, "template_id": tid, "consent_confirmed": True})) == 202
        await _drain()
        await WhatsAppContact.find({"whatsapp_agent_id": agent_id}).update({"$set": {"send_status": "pending"}})
    import json as _json

    assert {tuple(_json.loads(p["content_variables"])) for p in posted} == {("1", "2"), ("1",)}

    # Removing the link never deletes the template in Twilio.
    deleted = []
    monkeypatch.setattr("agents_service.whatsapp.twilio_client.TwilioClient.delete_template", lambda self, sid: deleted.append(sid))
    assert code(await client.delete(f"{base}/templates/{ok['id']}")) == 200 and deleted == []


async def test_refresh_status_fetches_from_twilio_and_stores_the_response(client, monkeypatch):
    set_auth(client.app, "u1", "org-1")
    agent_id = await _agent(client)
    base = f"/api/v1/whatsapp/agents/{agent_id}"
    await _upload(client, agent_id)
    # Simulated messages are not known to Twilio.
    batch_id = data(await client.get(f"{base}/batches"))[0]["id"]
    await client.post(f"{base}/send", json={"batch_id": batch_id, "consent_confirmed": True})
    await _drain()
    sim = data(await client.post(f"{base}/messages/refresh"))
    assert sim["checked"] == 0 and sim["simulated"] == 2

    # Pretend these were real messages that Twilio now reports as delivered / failed.
    contacts = await WhatsAppContact.find({"whatsapp_agent_id": agent_id}).to_list()
    for n, c in enumerate(contacts):
        c.twilio_message_sid, c.twilio_status = f"SM{n}", "queued"
        await c.save()
    states = {
        "SM0": {"MessageSid": "SM0", "MessageStatus": "delivered", "To": "whatsapp:+919876543210", "DateSent": "x"},
        "SM1": {"MessageSid": "SM1", "MessageStatus": "undelivered", "ErrorCode": "63016", "ErrorMessage": "Template needed"},
    }

    async def fake_fetch(self, sid):
        return states[sid]

    monkeypatch.setattr("agents_service.whatsapp.twilio_client.TwilioClient.fetch_message", fake_fetch)
    res = data(await client.post(f"{base}/messages/refresh"))
    assert res == {"checked": 2, "updated": 2, "errors": 0, "simulated": 0}
    rows = {m["message_sid"]: m for m in data(await client.get(f"{base}/messages"))["items"]}
    assert rows["SM0"]["status"] == "delivered" and rows["SM1"]["status"] == "undelivered"
    assert rows["SM1"]["error_code"] == "63016"
    events = data(await client.get(f"{base}/messages/{rows['SM0']['contact_id']}/events"))
    assert events[-1]["source"] == "refresh" and events[-1]["payload"]["To"] == "whatsapp:+919876543210"
    # Delivered can still become read, so it stays refreshable; failed is final and is skipped.
    assert data(await client.post(f"{base}/messages/refresh"))["checked"] == 1
    # Nothing changed -> no duplicate event.
    assert len(data(await client.get(f"{base}/messages/{rows['SM0']['contact_id']}/events"))) == len(events)
    # Specific contacts can be forced, even when final.
    forced = data(await client.post(f"{base}/messages/refresh", json={"contact_ids": [rows["SM1"]["contact_id"]]}))
    assert forced["checked"] == 1 and forced["updated"] == 0


SID = "AC" + "a" * 32
TOKEN = "t0ken" + "x" * 27


async def test_settings_are_per_org_and_never_leak_the_token(client):
    set_auth(client.app, "admin1", "org-1")
    empty = data(await client.get("/api/v1/whatsapp/settings"))
    assert empty["simulated"] is True and empty["has_auth_token"] is False and empty["dry_run"] is True

    saved = await client.put(
        "/api/v1/whatsapp/settings",
        json={"twilio_account_sid": SID, "auth_token": TOKEN, "twilio_whatsapp_from": "+1 415 555 0100",
              "default_country_code": "+44"},
    )
    out = data(saved)
    assert out["has_auth_token"] and out["auth_token_hint"] == "••••" + TOKEN[-4:]
    assert out["twilio_whatsapp_from"] == "+14155550100" and out["default_country_code"] == "44"
    assert "webhook_base_url" not in out and "status_callback_url" not in out  # nothing to configure
    assert TOKEN not in saved.text and TOKEN not in (await client.get("/api/v1/whatsapp/settings")).text

    stored = await WhatsAppSettings.find_one(WhatsAppSettings.org_id == "org-1")
    assert TOKEN not in stored.twilio_auth_token_enc and crypto.decrypt(stored.twilio_auth_token_enc) == TOKEN

    # Omitting the token on a later save keeps it.
    kept = data(await client.put("/api/v1/whatsapp/settings", json={"dry_run": False}))
    assert kept["has_auth_token"] and kept["simulated"] is False

    set_auth(client.app, "admin2", "org-2")  # another org sees none of it
    other = data(await client.get("/api/v1/whatsapp/settings"))
    assert other["twilio_account_sid"] == "" and other["simulated"] is True


async def test_settings_validation_and_permissions(client):
    set_auth(client.app, "dev", "org-1", Role.DEVELOPER)
    assert code(await client.get("/api/v1/whatsapp/settings")) == 200
    assert error_type(await client.put("/api/v1/whatsapp/settings", json={"dry_run": True})) == "FORBIDDEN"

    set_auth(client.app, "admin", "org-1")
    put = lambda body: client.put("/api/v1/whatsapp/settings", json=body)  # noqa: E731
    assert error_type(await put({"twilio_account_sid": "nope"})) == "UNPROCESSABLE_ENTITY"
    assert error_type(await put({"default_country_code": "abc"})) == "UNPROCESSABLE_ENTITY"
    assert error_type(await put({"dry_run": False})) == "UNPROCESSABLE_ENTITY"  # no credentials yet
    set_auth(client.app, "root", None, Role.SUPER_ADMIN)
    assert error_type(await put({"dry_run": True})) == "BAD_REQUEST"  # no org selected


async def test_org_country_code_applies_to_uploads(client):
    set_auth(client.app, "admin", "org-1")
    await client.put("/api/v1/whatsapp/settings", json={"default_country_code": "44"})
    agent_id = await _agent(client)
    await _upload(client, agent_id, "customer_name,phone_number,message\nAnn,7911123456,hi\n")
    items = data(await client.get(f"/api/v1/whatsapp/agents/{agent_id}/contacts"))["items"]
    assert items[0]["phone_number"] == 447911123456


async def test_connection_test_in_dry_run(client):
    set_auth(client.app, "admin", "org-1")
    res = data(await client.post("/api/v1/whatsapp/settings/test"))
    assert res["ok"] is True


async def test_status_callback_verifies_with_the_orgs_own_token(client):
    set_auth(client.app, "admin", "org-1")
    await client.put(
        "/api/v1/whatsapp/settings",
        json={"twilio_account_sid": SID, "auth_token": TOKEN, "dry_run": False},
    )
    agent_id = await _agent(client)
    await WhatsAppContact(org_id="org-1", whatsapp_agent_id=agent_id, customer_name="A", phone_number=919876543210,
                          message="m", send_status="sent", twilio_message_sid="SM1").insert()
    url = "https://api.example.com/api/v1/whatsapp/twilio/status-callback"
    body = "MessageSid=SM1&MessageStatus=delivered"
    # The gateway tells us the public URL it was reached on; Twilio signed that URL.
    hdr = {"Content-Type": "application/x-www-form-urlencoded", "X-Public-Base-Url": "https://api.example.com"}
    path = "/api/v1/whatsapp/twilio/status-callback"

    assert error_type(await client.post(path, content=body, headers=hdr)) == "FORBIDDEN"
    wrong = compute_signature("another-orgs-token-xxxxxxxx", url, {"MessageSid": "SM1", "MessageStatus": "delivered"})
    assert error_type(await client.post(path, content=body, headers={**hdr, "X-Twilio-Signature": wrong})) == "FORBIDDEN"
    sig = compute_signature(TOKEN, url, {"MessageSid": "SM1", "MessageStatus": "delivered"})
    assert code(await client.post(path, content=body, headers={**hdr, "X-Twilio-Signature": sig})) == 200
    contact = await WhatsAppContact.find_one(WhatsAppContact.twilio_message_sid == "SM1")
    assert contact.send_status == "delivered"
    # An unknown SID is acknowledged and ignored.
    assert code(await client.post(path, content="MessageSid=SMnope&MessageStatus=failed", headers=hdr)) == 200


async def test_callback_url_is_derived_from_the_gateways_public_url():
    from agents_service.whatsapp.twilio_client import callback_url

    assert callback_url("https://api.example.com/") == "https://api.example.com/api/v1/whatsapp/twilio/status-callback"
    assert callback_url("http://localhost:8000") is None  # Twilio can't reach it
    assert callback_url("http://127.0.0.1:8000") is None
    assert callback_url(None) is None


async def test_send_hands_twilio_the_callback_from_the_gateway_header(client, monkeypatch):
    seen = []

    async def fake_send(self, **kwargs):
        seen.append(kwargs.get("status_callback"))
        return "DRYfake"

    monkeypatch.setattr("agents_service.whatsapp.twilio_client.TwilioClient.send_message", fake_send)
    set_auth(client.app, "u1", "org-1")
    agent_id = await _agent(client)
    batch_id = data(await _upload(client, agent_id))["batch"]["id"]
    await client.post(
        f"/api/v1/whatsapp/agents/{agent_id}/send",
        json={"batch_id": batch_id, "consent_confirmed": True},
        headers={"X-Public-Base-Url": "https://api.example.com"},
    )
    await _drain()
    assert seen == ["https://api.example.com/api/v1/whatsapp/twilio/status-callback"] * 2


async def test_checkbox_field_type_is_stored_as_a_boolean():
    from agents_service.whatsapp.service import coerce_value

    assert [coerce_value(v, "checkbox") for v in ("true", "Yes", "x", "1")] == [True] * 4
    assert [coerce_value(v, "checkbox") for v in ("false", "no", "0", "unchecked")] == [False] * 4
    with pytest.raises(ValueError):
        coerce_value("maybe", "checkbox")


async def test_sms_agents_are_separate_and_send_plain_text(client, monkeypatch):
    set_auth(client.app, "admin", "org-1")
    wa = await _agent(client, "WA")
    created = await client.post("/api/v1/whatsapp/agents", json={"name": "SMS reminders", "channel": "sms", "twilio_sender": "MG" + "a" * 32})
    assert code(created) == 201 and data(created)["channel"] == "sms" and data(created)["twilio_sender"] == "MG" + "a" * 32
    sms = data(created)["id"]

    async def listed(ch):
        return [a["name"] for a in data(await client.get("/api/v1/whatsapp/agents", params={"channel": ch}))]

    assert await listed("sms") == ["SMS reminders"] and await listed("whatsapp") == ["WA"]
    bad = await client.post("/api/v1/whatsapp/agents", json={"name": "x", "channel": "sms", "twilio_sender": "nope"})
    assert error_type(bad) == "UNPROCESSABLE_ENTITY"

    base = f"/api/v1/whatsapp/agents/{sms}"
    await _upload(client, sms, "full_name,phone_number,message\nAsha,9876543210,Hi Asha\nRavi,9123456780,\n")
    # SMS templates need no approval and can't be submitted or imported from Twilio.
    t = data(await client.post(f"{base}/templates", json={"name": "due", "body": "Hi {{full_name}}, pay soon"}))
    assert t["approval_status"] == "approved" and t["twilio_content_sid"] is None
    assert error_type(await client.post(f"{base}/templates/{t['id']}/submit")) == "CONFLICT"
    assert data(await client.get(f"{base}/twilio-templates")) == []
    edited = data(await client.patch(f"{base}/templates/{t['id']}", json={"body": "Hello {{full_name}}"}))
    assert edited["body"] == "Hello {{full_name}}" and edited["approval_status"] == "approved"

    posted = []

    async def fake_send(self, **kwargs):
        posted.append(kwargs)
        return "DRYsms"

    monkeypatch.setattr("agents_service.whatsapp.twilio_client.TwilioClient.send_message", fake_send)
    batch_id = data(await client.get(f"{base}/batches"))[0]["id"]
    # Without a template each contact's own message goes out; Ravi has none and fails.
    assert code(await client.post(f"{base}/send", json={"batch_id": batch_id, "consent_confirmed": True})) == 202
    await _drain()
    assert [(p["body"], p["channel"]) for p in posted] == [("Hi Asha", "sms")]
    stats = data(await client.get(f"{base}/stats"))
    assert stats["sent"] == 1 and stats["failed"] == 1
    # With a template the text is rendered per contact.
    posted.clear()
    assert code(await client.post(f"{base}/send", json={"batch_id": batch_id, "template_id": t["id"], "consent_confirmed": True})) == 202
    await _drain()
    assert [p["body"] for p in posted] == ["Hello Ravi"]
