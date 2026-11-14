"""Client for Nessie, Capital One's hackathon mock bank API. All money is mock money.

Reads and writes are deliberately two separate classes:

- ``NessieReadClient``  - GET only. Any module may use it.
- ``NessieWriteClient`` - adds POST/PUT. Later, ``payer.py`` must be the ONLY
  application module that imports it (the seed/check scripts may too). Keeping
  the write methods in their own class makes that rule easy to check with grep.

Use ``get_read_client()`` / ``get_write_client()`` to get the real client, or the
in-memory mock from ``nessie_mock.py`` when DEMO_OFFLINE is set.

Where the paths and field names come from (the live docs page at
https://api.nessieisreal.com/documentation was not reachable when this was written):

- CONFIRMED from Nessie's official SDK sources (github.com/nessieisreal,
  javascript + android SDKs): every path and HTTP method used below, the key
  being sent as the ``key`` query parameter, the JSON field names of customer,
  account, merchant, bill and purchase, bill statuses, and the POST response
  wrapper ``{"code", "message", "objectCreated"}``.
- UNVERIFIED (never run against the live API, no key on the dev machine): the
  exact error body shape (we assume ``{"code", "message"}``), the body Nessie
  returns for PUT /bills/{id} (we assume ``{"code", "message"}``), whether Nessie
  sends a request-id header, and whether a purchase changes the account balance.
"""

import asyncio
import logging
import math
import re
import time

import httpx

NESSIE_TIMEOUT_S = 5.0  # one retry on timeout / connection error / 5xx (see _send)

BILL_STATUSES = ("pending", "cancelled", "completed", "recurring")
PURCHASE_MEDIUMS = ("balance", "rewards")

_ID_RE = re.compile(r"[A-Za-z0-9-]{1,64}\Z")  # real Nessie ids are UUIDs with hyphens
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_KEY_IN_TEXT_RE = re.compile(r"(key=)[^&\s\"']+")
_RETRY_PAUSE_S = 0.2


class NessieError(Exception):
    """Any failed Nessie call. ``status_code`` is None when no HTTP response exists
    (timeout, connection error, or input rejected before a request was sent)."""

    def __init__(self, status_code: int | None, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Nessie error ({status_code}): {message}")


# --- input checks (shared with nessie_mock.py) --------------------------------

def check_id(name: str, value: str) -> str:
    """Ids are put into URL paths, so only letters, digits and hyphens are allowed."""
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise NessieError(None, f"invalid {name}: must be letters, digits and hyphens only")
    return value


def check_amount(name: str, value: float) -> float:
    """Dollar amounts must be real numbers greater than zero."""
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not is_number or not math.isfinite(value) or value <= 0:
        raise NessieError(None, f"invalid {name}: must be a number greater than 0")
    return value


def check_date(name: str, value: str) -> str:
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise NessieError(None, f"invalid {name}: must be YYYY-MM-DD")
    return value


def check_choice(name: str, value: str, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        raise NessieError(None, f"invalid {name}: must be one of {', '.join(allowed)}")
    return value


def check_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NessieError(None, f"invalid {name}: must not be empty")
    return value


def check_balance(name: str, value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise NessieError(None, f"invalid {name}: must be a whole number, 0 or more")
    return value


# --- keeping the API key out of logs -------------------------------------------

class _RedactKeyFilter(logging.Filter):
    """httpx logs every request URL at INFO level, and our URL holds ?key=...
    This filter rewrites those log lines so the key is never written anywhere."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            text = record.getMessage()
        except Exception:
            return True
        if "key=" in text:
            record.msg = _KEY_IN_TEXT_RE.sub(r"\1[redacted]", text)
            record.args = ()
        return True


_redact_filter = _RedactKeyFilter()
for _logger_name in ("httpx", "httpcore"):
    logging.getLogger(_logger_name).addFilter(_redact_filter)


# --- clients -------------------------------------------------------------------

class NessieReadClient:
    """Read-only Nessie client (GET requests only)."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 timeout: float = NESSIE_TIMEOUT_S,
                 transport: httpx.AsyncBaseTransport | None = None):
        if base_url is None or api_key is None:
            # Lazy import: config is only needed when the caller gave no values.
            from app.config import get_settings
            settings = get_settings()
            if base_url is None:
                base_url = settings.nessie_base_url
            if api_key is None:
                api_key = settings.nessie_api_key
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=timeout,
                                       transport=transport)
        # Details of the most recent call, for audit logging. Never holds the key.
        self.last_response_meta: dict = {}

    def __repr__(self) -> str:
        return f"{type(self).__name__}(base_url={self.base_url!r})"  # no key here

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    # -- reads --

    async def get_customer(self, customer_id: str) -> dict:
        return await self._get_dict(f"/customers/{check_id('customer_id', customer_id)}")

    async def list_customers(self) -> list[dict]:
        return await self._get_list("/customers")

    async def list_customer_accounts(self, customer_id: str) -> list[dict]:
        return await self._get_list(
            f"/customers/{check_id('customer_id', customer_id)}/accounts")

    async def get_account(self, account_id: str) -> dict:
        return await self._get_dict(f"/accounts/{check_id('account_id', account_id)}")

    async def list_merchants(self) -> list[dict]:
        return await self._get_list("/merchants")

    async def get_merchant(self, merchant_id: str) -> dict:
        return await self._get_dict(f"/merchants/{check_id('merchant_id', merchant_id)}")

    async def list_account_bills(self, account_id: str) -> list[dict]:
        return await self._get_list(
            f"/accounts/{check_id('account_id', account_id)}/bills")

    async def get_bill(self, bill_id: str) -> dict:
        return await self._get_dict(f"/bills/{check_id('bill_id', bill_id)}")

    async def list_account_purchases(self, account_id: str) -> list[dict]:
        return await self._get_list(
            f"/accounts/{check_id('account_id', account_id)}/purchases")

    # -- plumbing --

    async def _get_dict(self, path: str) -> dict:
        data = await self._send("GET", path)
        if not isinstance(data, dict):
            raise NessieError(None, f"unexpected response for GET {path}: not an object")
        return data

    async def _get_list(self, path: str) -> list[dict]:
        data = await self._send("GET", path)
        if not isinstance(data, list):
            raise NessieError(None, f"unexpected response for GET {path}: not a list")
        return data

    async def _send(self, method: str, path: str, body: dict | None = None):
        """Send one request (with at most one retry) and return the parsed JSON.

        Retry rules - exactly one retry, and never for a 4xx:
        - GET: retry on timeout, connection error or 5xx. Reading twice is harmless.
        - POST/PUT: retry ONLY when the connection was never made (connect error or
          connect timeout), so we are certain Nessie did not get the request. After
          a read timeout or a 5xx the server may already have acted; sending a
          purchase again could charge the account twice, so we give up instead.
        """
        if not self._api_key:
            raise NessieError(None, "NESSIE_API_KEY is not set")
        is_read = method == "GET"
        started = time.monotonic()
        failure = NessieError(None, f"{method} {path} failed")

        for attempt in (1, 2):
            may_retry = False
            try:
                response = await self._http.request(
                    method, path, params={"key": self._api_key}, json=body)
            except (httpx.ConnectError, httpx.ConnectTimeout):
                # Nothing was sent, so a retry is safe for reads and writes alike.
                failure = NessieError(None, f"could not connect for {method} {path}")
                may_retry = True
            except httpx.TimeoutException:
                failure = NessieError(None, f"timed out waiting for {method} {path}")
                may_retry = is_read
            except httpx.HTTPError as exc:
                # Only the error's class name is used: httpx messages and request
                # objects can contain the full URL, which includes the key.
                failure = NessieError(
                    None, f"network error ({type(exc).__name__}) for {method} {path}")
                may_retry = is_read
            else:
                self._remember(method, path, response, started, attempt)
                if response.status_code < 500:
                    return self._parse(method, path, response)
                failure = NessieError(response.status_code,
                                      self._error_message(response))
                may_retry = is_read

            if attempt == 1 and may_retry:
                await asyncio.sleep(_RETRY_PAUSE_S)
                continue
            if failure.status_code is None:
                self._remember(method, path, None, started, attempt)
            # "from None" drops the httpx exception, which carries the keyed URL.
            raise failure from None

    def _remember(self, method: str, path: str, response: httpx.Response | None,
                  started: float, attempts: int) -> None:
        self.last_response_meta = {
            "method": method,
            "path": path,  # path only - the key is a query param and is left out
            "status": response.status_code if response is not None else None,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "attempts": attempts,
            # UNVERIFIED: Nessie may not send a request id; this is None if absent.
            "request_id": response.headers.get("x-request-id") if response is not None else None,
        }

    def _parse(self, method: str, path: str, response: httpx.Response):
        if not 200 <= response.status_code < 300:
            raise NessieError(response.status_code, self._error_message(response))
        try:
            return response.json()
        except ValueError:
            raise NessieError(response.status_code,
                              f"invalid JSON in response for {method} {path}") from None

    def _error_message(self, response: httpx.Response) -> str:
        """Use Nessie's own message when it sent one, and never echo the key."""
        message = f"HTTP {response.status_code}"
        try:
            data = response.json()
        except ValueError:
            data = None
        if isinstance(data, dict) and data.get("message"):
            message = str(data["message"])
            if data.get("culprit"):
                message += f" ({data['culprit']})"
        elif isinstance(data, str) and data.strip():
            # Seen live: validation errors come back as a bare JSON string.
            message = " ".join(data.split())
        if self._api_key:
            message = message.replace(self._api_key, "[redacted]")
        return message[:300]


class NessieWriteClient(NessieReadClient):
    """Nessie client that can also create and change things (POST/PUT).

    Only payer.py (and the seed/check scripts) should import this class.
    """

    async def create_customer(self, first_name: str, last_name: str, address: dict) -> dict:
        body = {
            "first_name": check_text("first_name", first_name),
            "last_name": check_text("last_name", last_name),
            "address": address,
        }
        return await self._create("/customers", body)

    async def create_account(self, customer_id: str, account_type: str, nickname: str,
                             balance: int, rewards: int = 0) -> dict:
        body = {
            "type": check_text("account_type", account_type),
            "nickname": check_text("nickname", nickname),
            "rewards": check_balance("rewards", rewards),
            "balance": check_balance("balance", balance),
        }
        return await self._create(
            f"/customers/{check_id('customer_id', customer_id)}/accounts", body)

    async def create_merchant(self, name: str, category: list[str], address: dict,
                              geocode: dict) -> dict:
        body = {
            "name": check_text("name", name),
            # Seen live: Nessie wants one string here and rejects a list with 400.
            "category": ", ".join(category),
            "address": address,
            "geocode": geocode,
        }
        return await self._create("/merchants", body)

    async def create_bill(self, account_id: str, status: str, payee: str,
                          payment_date: str, payment_amount: float,
                          nickname: str = "", recurring_date: int = 1) -> dict:
        body = {
            "status": check_choice("status", status, BILL_STATUSES),
            "payee": check_text("payee", payee),
            "payment_date": check_date("payment_date", payment_date),
            "recurring_date": recurring_date,
            "payment_amount": check_amount("payment_amount", payment_amount),
        }
        if nickname:
            body["nickname"] = nickname
        return await self._create(
            f"/accounts/{check_id('account_id', account_id)}/bills", body)

    async def create_purchase(self, account_id: str, merchant_id: str, amount: float,
                              purchase_date: str, description: str,
                              medium: str = "balance") -> dict:
        body = {
            "merchant_id": check_id("merchant_id", merchant_id),
            "medium": check_choice("medium", medium, PURCHASE_MEDIUMS),
            "purchase_date": check_date("purchase_date", purchase_date),
            "amount": check_amount("amount", amount),
            # Seen live: "status" must be sent. Nessie accepts a purchase without
            # it, but then GET /accounts/{id}/purchases fails with 400 for that
            # account from then on.
            "status": "pending",
            "description": description,
        }
        return await self._create(
            f"/accounts/{check_id('account_id', account_id)}/purchases", body)

    async def update_bill_status(self, bill_id: str, status: str) -> dict:
        """PUT /bills/{id}. Returns Nessie's reply as-is, which is expected to be
        ``{"code": 202, "message": ...}`` and NOT the bill (UNVERIFIED). Call
        ``get_bill`` afterwards if you need the updated bill."""
        body = {"status": check_choice("status", status, BILL_STATUSES)}
        data = await self._send("PUT", f"/bills/{check_id('bill_id', bill_id)}", body)
        if not isinstance(data, dict):
            raise NessieError(None, "unexpected response for PUT bill: not an object")
        return data

    async def _create(self, path: str, body: dict) -> dict:
        """POST and unwrap {"code": 201, "message": ..., "objectCreated": {...}}."""
        data = await self._send("POST", path, body)
        created = data.get("objectCreated") if isinstance(data, dict) else None
        if not isinstance(created, dict):
            raise NessieError(None, f"unexpected response for POST {path}: no objectCreated")
        return created


# --- factories -----------------------------------------------------------------

def get_read_client():
    """Real read client, or the in-memory mock when DEMO_OFFLINE is on."""
    from app.config import get_settings
    if get_settings().demo_offline:
        from app.nessie_mock import MockNessieRead
        return MockNessieRead()
    return NessieReadClient()


def get_write_client():
    """Real write client, or the in-memory mock when DEMO_OFFLINE is on."""
    from app.config import get_settings
    if get_settings().demo_offline:
        from app.nessie_mock import MockNessieWrite
        return MockNessieWrite()
    return NessieWriteClient()
