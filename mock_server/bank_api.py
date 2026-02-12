from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

try:
    from flask import Flask, jsonify, request

    HAS_FLASK = True
except ImportError:  # pragma: no cover - exercised only when Flask is missing
    Flask = None
    jsonify = None
    request = None
    HAS_FLASK = False


_lock = Lock()


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


DEFAULT_ACCOUNTS: Dict[str, float] = {"A": 1000.0, "B": 1000.0}
STATE: Dict[str, Any] = {
    "accounts": dict(DEFAULT_ACCOUNTS),
    "processed_idempotency_keys": {},
    "tx_counter": 0,
    "bug_flags": {
        "allow_negative_balance": _env_flag("BANK_BUG_ALLOW_NEGATIVE", default=False),
        "duplicate_on_retry": _env_flag("BANK_BUG_DUPLICATE_ON_RETRY", default=False),
    },
}


def _handle_health() -> Tuple[int, Dict[str, Any]]:
    return 200, {"status": "ok"}


def _handle_balance(account: Optional[str]) -> Tuple[int, Dict[str, Any]]:
    with _lock:
        if account:
            if account not in STATE["accounts"]:
                return 404, {"error": f"Account {account} not found"}
            return 200, {"accounts": {account: STATE["accounts"][account]}}
        return 200, {"accounts": dict(STATE["accounts"])}


def _handle_deposit(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    account = body.get("account")
    amount = body.get("amount")

    if not isinstance(account, str):
        return 400, {"error": "`account` must be a string"}
    if not isinstance(amount, (int, float)):
        return 400, {"error": "`amount` must be numeric"}
    if amount <= 0:
        return 400, {"error": "`amount` must be > 0"}

    with _lock:
        STATE["accounts"].setdefault(account, 0.0)
        STATE["accounts"][account] += float(amount)
        STATE["tx_counter"] += 1
        tx_id = STATE["tx_counter"]

        return 200, {
            "transaction_id": tx_id,
            "account": account,
            "amount": float(amount),
            "balance": STATE["accounts"][account],
        }


def _handle_transfer(body: Dict[str, Any], idempotency_key: Optional[str]) -> Tuple[int, Dict[str, Any]]:
    from_account = body.get("from")
    to_account = body.get("to")
    amount = body.get("amount")

    if not isinstance(from_account, str):
        return 400, {"error": "`from` must be a string"}
    if not isinstance(to_account, str):
        return 400, {"error": "`to` must be a string"}
    if from_account == to_account:
        return 400, {"error": "`from` and `to` must be different accounts"}
    if not isinstance(amount, (int, float)):
        return 400, {"error": "`amount` must be numeric"}
    if amount <= 0:
        return 400, {"error": "`amount` must be > 0"}

    with _lock:
        if from_account not in STATE["accounts"] or to_account not in STATE["accounts"]:
            return 404, {"error": "Account not found"}

        bug_duplicate = bool(STATE["bug_flags"].get("duplicate_on_retry", False))

        if idempotency_key and (not bug_duplicate):
            cached = STATE["processed_idempotency_keys"].get(idempotency_key)
            if cached is not None:
                replay = dict(cached)
                replay["idempotent_replay"] = True
                return 200, replay

        amount_f = float(amount)
        allow_negative = bool(STATE["bug_flags"].get("allow_negative_balance", False))

        source_balance = STATE["accounts"][from_account]
        if (not allow_negative) and source_balance < amount_f:
            return 400, {"error": "Insufficient funds"}

        STATE["accounts"][from_account] -= amount_f
        STATE["accounts"][to_account] += amount_f
        STATE["tx_counter"] += 1

        response = {
            "transaction_id": STATE["tx_counter"],
            "from": from_account,
            "to": to_account,
            "amount": amount_f,
            "balances": {
                from_account: STATE["accounts"][from_account],
                to_account: STATE["accounts"][to_account],
            },
        }

        if idempotency_key and (not bug_duplicate):
            STATE["processed_idempotency_keys"][idempotency_key] = dict(response)

        return 200, response


def _normalize_accounts(raw_accounts: Any) -> Tuple[Optional[Dict[str, float]], Optional[str]]:
    if not isinstance(raw_accounts, dict):
        return None, "`accounts` must be a mapping"

    normalized_accounts: Dict[str, float] = {}
    for account, balance in raw_accounts.items():
        if not isinstance(account, str):
            return None, "Account names must be strings"
        if not isinstance(balance, (int, float)):
            return None, "Account balances must be numeric"
        normalized_accounts[account] = float(balance)

    return normalized_accounts, None


def _handle_reset(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    accounts = body.get("accounts", DEFAULT_ACCOUNTS)
    bug_flags = body.get("bug_flags", {})

    if not isinstance(bug_flags, dict):
        return 400, {"error": "`bug_flags` must be a mapping"}

    normalized_accounts, account_error = _normalize_accounts(accounts)
    if account_error:
        return 400, {"error": account_error}

    assert normalized_accounts is not None

    with _lock:
        STATE["accounts"] = normalized_accounts
        STATE["processed_idempotency_keys"] = {}
        STATE["tx_counter"] = 0

        STATE["bug_flags"]["allow_negative_balance"] = bool(
            bug_flags.get("allow_negative_balance", STATE["bug_flags"]["allow_negative_balance"])
        )
        STATE["bug_flags"]["duplicate_on_retry"] = bool(
            bug_flags.get("duplicate_on_retry", STATE["bug_flags"]["duplicate_on_retry"])
        )

        return 200, {
            "status": "reset",
            "accounts": dict(STATE["accounts"]),
            "bug_flags": dict(STATE["bug_flags"]),
        }


if HAS_FLASK:
    app = Flask(__name__)

    @app.get("/health")
    def health() -> Any:
        status, payload = _handle_health()
        return jsonify(payload), status


    @app.get("/balance")
    def get_balance() -> Any:
        account = request.args.get("account")
        status, payload = _handle_balance(account)
        return jsonify(payload), status


    @app.post("/deposit")
    def deposit() -> Any:
        body = request.get_json(silent=True) or {}
        status, payload = _handle_deposit(body)
        return jsonify(payload), status


    @app.post("/transfer")
    def transfer() -> Any:
        body = request.get_json(silent=True) or {}
        key = request.headers.get("Idempotency-Key")
        status, payload = _handle_transfer(body, key)
        return jsonify(payload), status


    @app.post("/reset")
    def reset() -> Any:
        body = request.get_json(silent=True) or {}
        status, payload = _handle_reset(body)
        return jsonify(payload), status

else:
    app = None

    class _BankRequestHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _read_json_body(self) -> Dict[str, Any]:
            content_length = int(self.headers.get("Content-Length", "0") or "0")
            if content_length <= 0:
                return {}
            raw = self.rfile.read(content_length)
            if not raw:
                return {}
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}

        def _write_json(self, status: int, payload: Dict[str, Any]) -> None:
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                status, payload = _handle_health()
            elif parsed.path == "/balance":
                account = parse_qs(parsed.query).get("account", [None])[0]
                status, payload = _handle_balance(account)
            else:
                status, payload = 404, {"error": "Not Found"}

            self._write_json(status, payload)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            body = self._read_json_body()

            if parsed.path == "/deposit":
                status, payload = _handle_deposit(body)
            elif parsed.path == "/transfer":
                status, payload = _handle_transfer(body, self.headers.get("Idempotency-Key"))
            elif parsed.path == "/reset":
                status, payload = _handle_reset(body)
            else:
                status, payload = 404, {"error": "Not Found"}

            self._write_json(status, payload)


    def _run_stdlib_server(host: str, port: int) -> None:
        server = ThreadingHTTPServer((host, port), _BankRequestHandler)
        try:
            server.serve_forever()
        finally:
            server.server_close()


if __name__ == "__main__":
    host = os.getenv("BANK_API_HOST", "0.0.0.0")
    port = int(os.getenv("BANK_API_PORT", "5000"))

    if HAS_FLASK:
        app.run(host=host, port=port, debug=False)
    else:
        print("Flask not installed; running stdlib fallback server")
        _run_stdlib_server(host, port)
