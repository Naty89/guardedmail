"""Tests for the real Nessie client. No network: httpx.MockTransport answers."""

import asyncio
import json
import logging

import httpx
import pytest

from app import nessie
from app.nessie import NessieError, NessieReadClient, NessieWriteClient

KEY = "testkey-SECRET-123"
BASE = "http://nessie.test"
CUST = "aaaaaaaaaaaaaaaaaaaaaaa1"
ACCT = "bbbbbbbbbbbbbbbbbbbbbbb2"
MERCH = "ccccccccccccccccccccccc3"
BILL = "ddddddddddddddddddddddd4"
ADDRESS = {"street_number": "1", "street_name": "Test St", "city": "Testville",
           "state": "MA", "zip": "01101"}


@pytest.fixture(autouse=True)
def no_retry_pause(monkeypatch):
    monkeypatch.setattr(nessie, "_RETRY_PAUSE_S", 0)


class Recorder:
    """Plays back a list of replies (or raises them) and records each request."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply


def ok(data, status=200):
    return httpx.Response(status, json=data)


def created(obj):
    return httpx.Response(201, json={"code": 201, "message": "Created", "objectCreated": obj})


def call(recorder, method_name, *args, client_class=NessieWriteClient, **kwargs):
    """Run one client method against the recorder and return its result."""
    async def run():
        async with client_class(base_url=BASE, api_key=KEY,
                                transport=httpx.MockTransport(recorder)) as client:
            result = await getattr(client, method_name)(*args, **kwargs)
            return result, client.last_response_meta
    return asyncio.run(run())


def body_of(request: httpx.Request) -> dict:
    return json.loads(request.content)


# --- reads ---------------------------------------------------------------------

@pytest.mark.parametrize("method_name, args, path, reply", [
    ("get_customer", (CUST,), f"/customers/{CUST}", {"_id": CUST}),
    ("list_customers", (), "/customers", [{"_id": CUST}]),
    ("list_customer_accounts", (CUST,), f"/customers/{CUST}/accounts", [{"_id": ACCT}]),
    ("get_account", (ACCT,), f"/accounts/{ACCT}", {"_id": ACCT, "balance": 2000}),
    ("list_merchants", (), "/merchants", [{"_id": MERCH}]),
    ("get_merchant", (MERCH,), f"/merchants/{MERCH}", {"_id": MERCH}),
    ("list_account_bills", (ACCT,), f"/accounts/{ACCT}/bills", [{"_id": BILL}]),
    ("get_bill", (BILL,), f"/bills/{BILL}", {"_id": BILL, "status": "pending"}),
    ("list_account_purchases", (ACCT,), f"/accounts/{ACCT}/purchases", []),
])
def test_read_methods_use_right_path_and_key(method_name, args, path, reply):
    recorder = Recorder(ok(reply))
    result, meta = call(recorder, method_name, *args, client_class=NessieReadClient)
    assert result == reply
    request = recorder.requests[0]
    assert request.method == "GET"
    assert request.url.path == path
    assert request.url.params["key"] == KEY
    assert meta["method"] == "GET" and meta["path"] == path and meta["status"] == 200
    assert meta["attempts"] == 1 and isinstance(meta["elapsed_ms"], int)
    assert KEY not in json.dumps(meta)


def test_read_client_has_no_write_methods():
    assert not hasattr(NessieReadClient, "create_purchase")
    assert not hasattr(NessieReadClient, "update_bill_status")


# --- writes --------------------------------------------------------------------

def test_create_customer():
    recorder = Recorder(created({"_id": CUST, "first_name": "Demo"}))
    result, _ = call(recorder, "create_customer", "Demo", "User", ADDRESS)
    assert result == {"_id": CUST, "first_name": "Demo"}
    request = recorder.requests[0]
    assert (request.method, request.url.path) == ("POST", "/customers")
    assert request.url.params["key"] == KEY
    assert body_of(request) == {"first_name": "Demo", "last_name": "User", "address": ADDRESS}


def test_create_account():
    recorder = Recorder(created({"_id": ACCT}))
    result, _ = call(recorder, "create_account", CUST, "Checking", "Demo Checking", 2000)
    assert result == {"_id": ACCT}
    request = recorder.requests[0]
    assert (request.method, request.url.path) == ("POST", f"/customers/{CUST}/accounts")
    assert body_of(request) == {"type": "Checking", "nickname": "Demo Checking",
                                "rewards": 0, "balance": 2000}


def test_create_merchant():
    recorder = Recorder(created({"_id": MERCH}))
    geocode = {"lat": 42.1, "lng": -72.5}
    result, _ = call(recorder, "create_merchant", "Test Electric", ["utilities"],
                     ADDRESS, geocode)
    assert result == {"_id": MERCH}
    request = recorder.requests[0]
    assert (request.method, request.url.path) == ("POST", "/merchants")
    assert body_of(request) == {"name": "Test Electric", "category": "utilities",
                                "address": ADDRESS, "geocode": geocode}


def test_create_bill():
    recorder = Recorder(created({"_id": BILL}))
    result, _ = call(recorder, "create_bill", ACCT, "pending", "Test Electric",
                     "2026-12-01", 84.12, nickname="Electric")
    assert result == {"_id": BILL}
    request = recorder.requests[0]
    assert (request.method, request.url.path) == ("POST", f"/accounts/{ACCT}/bills")
    assert body_of(request) == {"status": "pending", "payee": "Test Electric",
                                "payment_date": "2026-12-01", "recurring_date": 1,
                                "payment_amount": 84.12, "nickname": "Electric"}


def test_create_purchase():
    recorder = Recorder(created({"_id": "eeee5", "amount": 84.12}))
    result, meta = call(recorder, "create_purchase", ACCT, MERCH, 84.12,
                        "2026-11-14", "Electric bill")
    assert result == {"_id": "eeee5", "amount": 84.12}
    request = recorder.requests[0]
    assert (request.method, request.url.path) == ("POST", f"/accounts/{ACCT}/purchases")
    assert request.url.params["key"] == KEY
    assert body_of(request) == {"merchant_id": MERCH, "medium": "balance",
                                "purchase_date": "2026-11-14", "amount": 84.12,
                                "status": "pending", "description": "Electric bill"}
    assert meta["status"] == 201 and meta["method"] == "POST"


def test_update_bill_status():
    reply = {"code": 202, "message": "Accepted bill modification"}
    recorder = Recorder(ok(reply, status=202))
    result, _ = call(recorder, "update_bill_status", BILL, "completed")
    assert result == reply
    request = recorder.requests[0]
    assert (request.method, request.url.path) == ("PUT", f"/bills/{BILL}")
    assert request.url.params["key"] == KEY
    assert body_of(request) == {"status": "completed"}


def test_create_without_object_created_is_an_error():
    recorder = Recorder(ok({"code": 201, "message": "Created"}, status=201))
    with pytest.raises(NessieError):
        call(recorder, "create_customer", "Demo", "User", ADDRESS)


# --- errors --------------------------------------------------------------------

def test_404_raises_with_status_and_nessie_message():
    recorder = Recorder(ok({"code": 404, "message": "This id does not exist"}, status=404))
    with pytest.raises(NessieError) as caught:
        call(recorder, "get_account", ACCT)
    assert caught.value.status_code == 404
    assert caught.value.message == "This id does not exist"
    assert len(recorder.requests) == 1  # a 4xx is never retried


def test_4xx_on_write_is_not_retried():
    recorder = Recorder(ok({"code": 400, "message": "Bad body"}, status=400))
    with pytest.raises(NessieError) as caught:
        call(recorder, "create_purchase", ACCT, MERCH, 5, "2026-11-14", "x")
    assert caught.value.status_code == 400
    assert len(recorder.requests) == 1


def test_invalid_json_raises():
    recorder = Recorder(httpx.Response(200, text="<html>not json</html>"))
    with pytest.raises(NessieError) as caught:
        call(recorder, "get_account", ACCT)
    assert "invalid JSON" in caught.value.message


def test_wrong_shape_raises():
    with pytest.raises(NessieError):
        call(Recorder(ok({"not": "a list"})), "list_merchants")
    with pytest.raises(NessieError):
        call(Recorder(ok(["not", "a dict"])), "get_account", ACCT)


def test_missing_api_key_raises_before_any_request():
    recorder = Recorder(ok({}))

    async def run():
        client = NessieReadClient(base_url=BASE, api_key="",
                                  transport=httpx.MockTransport(recorder))
        await client.get_account(ACCT)

    with pytest.raises(NessieError):
        asyncio.run(run())
    assert recorder.requests == []


# --- retries -------------------------------------------------------------------

@pytest.mark.parametrize("first_failure", [
    httpx.ReadTimeout("slow"),
    httpx.ConnectError("refused"),
    httpx.Response(503, json={"message": "down"}),
])
def test_read_retries_once_then_succeeds(first_failure):
    recorder = Recorder(first_failure, ok({"_id": ACCT}))
    result, meta = call(recorder, "get_account", ACCT)
    assert result == {"_id": ACCT}
    assert len(recorder.requests) == 2
    assert meta["attempts"] == 2 and meta["status"] == 200


def test_read_gives_up_after_second_timeout():
    recorder = Recorder(httpx.ReadTimeout("slow"), httpx.ReadTimeout("slow"),
                        ok({"_id": ACCT}))
    with pytest.raises(NessieError) as caught:
        call(recorder, "get_account", ACCT)
    assert caught.value.status_code is None
    assert len(recorder.requests) == 2


def test_read_gives_up_after_second_5xx():
    recorder = Recorder(httpx.Response(500, json={"message": "boom"}),
                        httpx.Response(502, text="bad gateway"), ok({"_id": ACCT}))
    with pytest.raises(NessieError) as caught:
        call(recorder, "get_account", ACCT)
    assert caught.value.status_code == 502
    assert len(recorder.requests) == 2


@pytest.mark.parametrize("failure", [
    httpx.ReadTimeout("slow"),
    httpx.ReadError("connection dropped"),
    httpx.Response(500, json={"message": "boom"}),
])
def test_purchase_is_not_retried_when_it_may_have_reached_nessie(failure):
    recorder = Recorder(failure, created({"_id": "eeee5"}))
    with pytest.raises(NessieError):
        call(recorder, "create_purchase", ACCT, MERCH, 84.12, "2026-11-14", "x")
    assert len(recorder.requests) == 1  # a second POST could double-charge


def test_bill_update_is_not_retried_on_5xx():
    recorder = Recorder(httpx.Response(500, json={"message": "boom"}), ok({"code": 202}))
    with pytest.raises(NessieError):
        call(recorder, "update_bill_status", BILL, "completed")
    assert len(recorder.requests) == 1


@pytest.mark.parametrize("failure", [httpx.ConnectError("refused"),
                                     httpx.ConnectTimeout("no route")])
def test_purchase_is_retried_once_when_connection_never_opened(failure):
    recorder = Recorder(failure, created({"_id": "eeee5"}))
    result, _ = call(recorder, "create_purchase", ACCT, MERCH, 84.12, "2026-11-14", "x")
    assert result == {"_id": "eeee5"}
    assert len(recorder.requests) == 2


# --- the key must never leak ---------------------------------------------------

@pytest.mark.parametrize("failure", [
    httpx.ReadTimeout(f"timeout on {BASE}/accounts/x?key={KEY}"),
    httpx.ConnectError(f"refused {BASE}/accounts/x?key={KEY}"),
    httpx.Response(500, json={"message": f"failed for /accounts/x?key={KEY}"}),
    httpx.Response(401, json={"message": f"bad key {KEY}"}),
    httpx.Response(404, text=f"not found ?key={KEY}"),
])
def test_key_never_appears_in_errors(failure):
    recorder = Recorder(failure)
    with pytest.raises(NessieError) as caught:
        call(recorder, "get_account", ACCT)
    error = caught.value
    assert KEY not in str(error)
    assert KEY not in repr(error)
    assert KEY not in error.message
    # The httpx error (which may hold the keyed URL) is not shown in tracebacks.
    assert error.__cause__ is None
    assert error.__context__ is None or error.__suppress_context__


def test_key_not_in_repr_or_logs(caplog):
    client = NessieWriteClient(base_url=BASE, api_key=KEY,
                               transport=httpx.MockTransport(Recorder(ok({"_id": ACCT}))))
    assert KEY not in repr(client)
    assert KEY not in str(client)
    with caplog.at_level(logging.DEBUG):
        asyncio.run(client.get_account(ACCT))
        asyncio.run(client.aclose())
    assert "/accounts/" in caplog.text  # httpx did log the request...
    assert KEY not in caplog.text       # ...but without the key


# --- input checks happen before any request ------------------------------------

@pytest.mark.parametrize("method_name, args", [
    ("get_customer", ("",)),
    ("get_account", ("../customers",)),
    ("get_account", ("abc/def",)),
    ("get_account", ("abc?key=x",)),
    ("get_account", ("abc def",)),
    ("get_account", (None,)),
    ("get_merchant", ("a.b",)),
    ("get_bill", ("a#b",)),
    ("list_customer_accounts", ("a/b",)),
    ("list_account_bills", ("",)),
    ("list_account_purchases", ("%2e%2e",)),
    ("create_account", ("bad/id", "Checking", "Nick", 100)),
    ("create_account", (CUST, "Checking", "Nick", -5)),
    ("create_bill", ("bad id", "pending", "Payee", "2026-12-01", 10.0)),
    ("create_bill", (ACCT, "paid", "Payee", "2026-12-01", 10.0)),
    ("create_bill", (ACCT, "pending", "Payee", "next week", 10.0)),
    ("create_bill", (ACCT, "pending", "Payee", "2026-12-01", 0)),
    ("create_purchase", ("bad/id", MERCH, 10.0, "2026-11-14", "x")),
    ("create_purchase", (ACCT, "bad/id", 10.0, "2026-11-14", "x")),
    ("create_purchase", (ACCT, MERCH, 0, "2026-11-14", "x")),
    ("create_purchase", (ACCT, MERCH, -5.0, "2026-11-14", "x")),
    ("create_purchase", (ACCT, MERCH, float("nan"), "2026-11-14", "x")),
    ("create_purchase", (ACCT, MERCH, float("inf"), "2026-11-14", "x")),
    ("create_purchase", (ACCT, MERCH, "10", "2026-11-14", "x")),
    ("create_purchase", (ACCT, MERCH, True, "2026-11-14", "x")),
    ("create_purchase", (ACCT, MERCH, 10.0, "14/11/2026", "x")),
    ("create_purchase", (ACCT, MERCH, 10.0, "2026-11-14", "x", "cash")),
    ("update_bill_status", ("bad/id", "completed")),
    ("update_bill_status", (BILL, "done")),
])
def test_bad_input_rejected_before_any_request(method_name, args):
    recorder = Recorder(ok({}))
    with pytest.raises(NessieError) as caught:
        call(recorder, method_name, *args)
    assert caught.value.status_code is None
    assert recorder.requests == []


# --- config and factories ------------------------------------------------------

def _config_or_skip():
    try:
        import app.config  # noqa: F401  (Agent A's module)
    except ImportError:
        pytest.skip("app/config.py does not exist yet")


def test_factories_return_mocks_when_demo_offline(monkeypatch):
    _config_or_skip()
    from app.nessie_mock import MockNessieRead, MockNessieWrite
    monkeypatch.setenv("DEMO_OFFLINE", "1")
    assert type(nessie.get_read_client()) is MockNessieRead
    assert type(nessie.get_write_client()) is MockNessieWrite


def test_factories_return_real_clients_when_online(monkeypatch):
    _config_or_skip()
    monkeypatch.setenv("DEMO_OFFLINE", "0")
    monkeypatch.setenv("NESSIE_API_KEY", KEY)
    monkeypatch.setenv("NESSIE_BASE_URL", BASE + "/")
    read_client = nessie.get_read_client()
    write_client = nessie.get_write_client()
    assert type(read_client) is NessieReadClient
    assert type(write_client) is NessieWriteClient
    assert read_client.base_url == BASE and write_client._api_key == KEY
    asyncio.run(read_client.aclose())
    asyncio.run(write_client.aclose())
