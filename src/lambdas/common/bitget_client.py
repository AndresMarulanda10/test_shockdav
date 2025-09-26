import hmac

import hashlib
import base64
import httpx
import json
from typing import Dict, Any, Optional

BASE = "https://api.bitget.com"


def sign_request(secret_key: str, timestamp: str, method: str, request_path: str, query_string: str = "", body_str: str = "") -> str:
    """Create Bitget HMAC-SHA256 + Base64 signature.

    message: timestamp + method + requestPath + query + body
    """
    if query_string and not query_string.startswith("?"):
        query_string = f"?{query_string}"
    message = f"{timestamp}{method.upper()}{request_path}{query_string}{body_str}"
    mac = hmac.new(secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()


async def get_orders_async(api_key: str, secret_key: str, passphrase: str, symbol: str, params: Optional[Dict[str, Any]] = None, timeout: int = 20, request_path: Optional[str] = None, use_seconds_timestamp: bool = False, method: str = "GET", body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fetch orders for a symbol from Bitget (async).

    Note: This function uses the Bitget endpoint `/api/v2/mix/order/orders-history` for futures history.
    It performs a signed GET request and returns the parsed JSON response.
    """
    params = params or {}
    # Allow caller to override the request path for probing multiple endpoint variants.
    request_path = request_path or "/api/v2/mix/order/orders-history"
    url = BASE + request_path

    # Use the provided method (default is GET). Build query string using httpx QueryParams
    method = method or "GET"
    query_string = str(httpx.QueryParams(params)) if params else ""

    import time
    # Bitget expects timestamp in milliseconds by default; some API variants use seconds.
    if use_seconds_timestamp:
        timestamp = str(int(time.time()))
    else:
        timestamp = str(int(time.time() * 1000))

    body_str = ""
    if body is not None:
        try:
            body_str = json.dumps(body, separators=(",", ":"))
        except Exception:
            body_str = str(body)
    signature = sign_request(secret_key, timestamp, method, request_path, query_string, body_str)

    headers = {
        "ACCESS-KEY": api_key,
        "ACCESS-SIGN": signature,
        "ACCESS-TIMESTAMP": timestamp,
        "ACCESS-PASSPHRASE": passphrase,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        if method.upper() == "GET":
            resp = await client.get(url, params=params, headers=headers)
        else:
            # For POST/PUT variants send JSON body
            resp = await client.request(method.upper(), url, params=params, json=body, headers=headers)
        resp.raise_for_status()
        return resp.json()


def extract_orders_response(resp: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize response structure to {'data': [...], 'code': '00000'} etc."""
    if isinstance(resp, dict) and ("data" in resp or "orders" in resp):
        return resp
    # Otherwise wrap
    return {"data": resp}
