import json
import os
import asyncio
from typing import List, Dict, Any
from src.lambdas.common.bitget_client import get_orders_async
from src.lambdas.common.aws_helpers import upload_json_to_s3, get_secret
import time
import random


S3_BUCKET = os.environ.get("RESULTS_BUCKET")
S3_PREFIX = os.environ.get("RESULTS_PREFIX", "per-symbol/")


def _make_s3_key(symbol: str) -> str:
    ts = int(time.time())
    return f"{S3_PREFIX}{symbol}/{ts}-{symbol}.json"


def handler(event, context):
    # support both direct invocation and Step Functions input
    symbol = None
    if isinstance(event, dict):
        symbol = event.get("symbol") or (event.get("input") or {}).get("symbol")

    if not symbol:
        return {"statusCode": 400, "body": json.dumps({"error": "symbol required"})}

    # Credentials from env (for local testing); in deployed Lambdas use Secrets Manager
    api_key = os.environ.get("BITGET_API_KEY")
    secret_key = os.environ.get("BITGET_API_SECRET")
    passphrase = os.environ.get("BITGET_API_PASSPHRASE")
    secret_name = os.environ.get("CREDENTIALS_SECRET_NAME")
    aws_region = os.environ.get("AWS_REGION")

    if secret_name and (not api_key or not secret_key):
        creds = get_secret(secret_name, aws_region)
        api_key = api_key or creds.get("apiKey") or creds.get("api_key")
        secret_key = secret_key or creds.get("secretKey") or creds.get("secret_key")
        passphrase = passphrase or creds.get("passphrase")

    all_orders: List[Dict[str, Any]] = []
    limit = 100
    id_less_than = None
    last_request_ts = 0.0

    try:
        while True:
            params = {"symbol": symbol, "limit": limit}
            if id_less_than:
                params["idLessThan"] = id_less_than

            # throttle local minimum interval 0.8s
            now = time.time()
            sleep_for = 0.8 - (now - last_request_ts)
            if sleep_for > 0:
                asyncio.run(asyncio.sleep(sleep_for))
            last_request_ts = time.time()

            # Retry/backoff loop for transient errors (429 / 5xx)
            attempts = 5
            resp = None
            for attempt in range(attempts):
                try:
                    resp = asyncio.run(get_orders_async(api_key, secret_key, passphrase, symbol, params))
                    break
                except Exception as e:
                    # Try to detect HTTP status code (httpx.HTTPStatusError or similar)
                    status = None
                    try:
                        status = getattr(e, 'response', None) and getattr(e.response, 'status_code', None)
                    except Exception:
                        status = None

                    # Retry only on 429 or 5xx
                    if status == 429 or (isinstance(status, int) and 500 <= status < 600):
                        if attempt < attempts - 1:
                            backoff = 0.5 * (2 ** attempt) + random.uniform(0, 0.1)
                            time.sleep(backoff)
                            continue
                    # non-retryable or out of attempts -> re-raise
                    raise

            if resp is None:
                break

            # Bitget may return data under 'data' or 'orders'
            page = resp.get("data") or resp.get("orders") or []
            if not page:
                break

            if isinstance(page, dict) and "orders" in page:
                page = page.get("orders")

            all_orders.extend(page)

            # Prepare next page: idLessThan uses the smallest id in current page
            try:
                ids = [int(item.get('id') or item.get('orderId') or 0) for item in page if item]
                if not ids:
                    break
                id_less_than = min(ids)
            except Exception:
                break

            # safety guard to avoid infinite loops
            if len(all_orders) >= 20000:
                break

    except Exception as e:
        return {"symbol": symbol, "error": str(e)}

    # If results are large, upload to S3 and return pointer
    payload_size = len(json.dumps(all_orders))
    if S3_BUCKET and payload_size > 250000:  # ~250KB threshold
        key = _make_s3_key(symbol)
        upload_json_to_s3(S3_BUCKET, key, {"symbol": symbol, "orders": all_orders})
        return {"symbol": symbol, "count": len(all_orders), "s3_key": key}

    return {"symbol": symbol, "count": len(all_orders), "orders": all_orders}
