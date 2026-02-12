import hashlib
import json
import logging
import time
import uuid
from typing import Any

import aiohttp

from db import get_user


BITUNIX_BASE_URL = "https://fapi.bitunix.com"
logger = logging.getLogger(__name__)


def canonical_query(params: dict | None) -> str:
    if not params:
        return ""

    items = sorted((str(k), "" if v is None else str(v)) for k, v in params.items())
    return "".join(f"{key}{value}" for key, value in items)


def compact_json(body: dict | None) -> str:
    if body is None:
        return ""
    return json.dumps(body, separators=(",", ":"))


def make_sign(
    api_key: str,
    api_secret: str,
    nonce: str,
    timestamp: str,
    query_canon: str,
    body_str: str,
) -> str:
    raw = f"{nonce}{timestamp}{api_key}{query_canon}{body_str}"
    first_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    final_hash = hashlib.sha256(f"{first_hash}{api_secret}".encode("utf-8")).hexdigest()
    return final_hash


async def bitunix_request(
    discord_id: str,
    method: str,
    path: str,
    params: dict | None = None,
    body: dict | None = None,
) -> dict[str, Any]:
    user = await get_user(discord_id)
    if user is None:
        raise Exception("Usuario no registrado. Usa /register_bitunix en DM.")

    api_key = str(user["api_key"])
    api_secret = str(user["api_secret"])
    method_upper = method.upper()
    timestamp = str(int(time.time() * 1000))
    nonce = uuid.uuid4().hex

    query_canon = canonical_query(params)
    body_str = "" if method_upper == "GET" else compact_json(body)
    sign = make_sign(api_key, api_secret, nonce, timestamp, query_canon, body_str)

    headers = {
        "api-key": api_key,
        "timestamp": timestamp,
        "nonce": nonce,
        "sign": sign,
    }
    if method_upper != "GET":
        headers["Content-Type"] = "application/json"

    url = f"{BITUNIX_BASE_URL}{path}"
    logger.info("Bitunix request path=%s params=%s", path, params)

    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.request(
            method_upper,
            url,
            params=params,
            data=body_str if method_upper != "GET" else None,
            headers=headers,
        ) as response:
            logger.info("Bitunix final URL=%s", str(response.url))
            response_text = await response.text()
            logger.info("Bitunix HTTP status=%s", response.status)

            if response.status != 200:
                raise Exception(f"HTTP {response.status}: {response_text[:400]}")

            try:
                payload = json.loads(response_text)
            except json.JSONDecodeError as exc:
                raise Exception(f"JSON invalido: {response_text[:400]}") from exc

    logger.info("Bitunix response JSON=%s", payload)

    if not isinstance(payload, dict):
        raise Exception("Respuesta inesperada: se esperaba objeto JSON.")

    code = payload.get("code")
    if code != 0 and code != "0":
        msg = payload.get("msg") or payload.get("message") or "Sin detalle"
        raise Exception(f"Bitunix code={code}, msg={msg}")

    return payload


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


async def fetch_user_trades(
    discord_id: str, symbol: str | None = None, limit: int = 50, skip: int = 0
) -> tuple[int, list[dict[str, Any]]]:
    safe_limit = max(1, min(limit, 100))
    params: dict[str, Any] = {"limit": safe_limit, "skip": max(0, skip)}
    if symbol:
        params["symbol"] = symbol

    response = await bitunix_request(
        discord_id=discord_id,
        method="GET",
        path="/api/v1/futures/trade/get_history_trades",
        params=params,
    )

    code = response.get("code")
    if code != 0 and code != "0":
        msg = response.get("msg") or response.get("message") or "Sin detalle"
        raise Exception(f"Bitunix code={code}, msg={msg}")

    data = response.get("data")
    trade_list = []
    if isinstance(data, dict):
        raw_trade_list = data.get("tradeList", [])
        if isinstance(raw_trade_list, list):
            trade_list = raw_trade_list

    normalized: list[dict[str, Any]] = []
    for item in trade_list:
        if not isinstance(item, dict):
            continue

        trade_id_val = item.get("tradeId")
        if trade_id_val is None:
            continue

        normalized.append(
            {
                "trade_id": str(trade_id_val),
                "symbol": str(item.get("symbol", "")),
                "timestamp_ms": _to_int(item.get("ctime"), 0),
                "side": str(item.get("side", "")),
                "qty": _to_float(item.get("qty"), 0.0),
                "price": _to_float(item.get("price"), 0.0),
                "realized_pnl": _to_float(item.get("realizedPNL"), 0.0),
                "fee": _to_float(item.get("fee"), 0.0),
                "raw_json": json.dumps(item, separators=(",", ":")),
            }
        )

    return len(normalized), normalized
