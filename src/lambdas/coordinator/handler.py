import json
import os
import boto3
from botocore.exceptions import ClientError
from src.lambdas.common.aws_helpers import get_secret
from src.lambdas.common import bitget_client


def _detect_symbols_by_scanning(api_key: str, secret_key: str, passphrase: str, product_type: str = "USDT-FUTURES", max_scan_orders: int = 2000, limit: int = 100):
    """Scan the orders-history (no symbol) and collect unique symbols using idLessThan pagination.

    Returns a list of symbol strings.
    """
    symbols = set()
    pages = 0
    scanned = 0
    id_less_than = None

    while True:
        pages += 1
        params = {"limit": limit}
        if product_type:
            params["productType"] = product_type
        if id_less_than:
            params["idLessThan"] = id_less_than

        try:
            # get_orders_async expects a symbol param; pass empty symbol and params to scan
            resp = bitget_client.get_orders_async(api_key, secret_key, passphrase, symbol="", params=params)
            # note: get_orders_async is async; call synchronously
            resp = __import__('asyncio').run(resp)
        except Exception:
            break

        page = resp.get("data") or resp.get("orders") or []
        if isinstance(page, dict) and "orders" in page:
            page = page.get("orders")
        if not page:
            break

        for item in page:
            if not item:
                continue
            s = item.get('symbol') or item.get('symbolName') or item.get('instrument_id') or item.get('instId')
            if s:
                symbols.add(s)

        scanned += len(page)

        try:
            ids = [int(item.get('id') or item.get('orderId') or 0) for item in page if item]
            if not ids:
                break
            id_less_than = min(ids)
        except Exception:
            break

        if scanned >= max_scan_orders:
            break

    return sorted(symbols)


def handler(event, context):
    """Coordinator: validates symbols and starts the Step Function execution."""
    aws_region = os.environ.get("AWS_REGION")
    state_machine_arn = os.environ.get("STATE_MACHINE_ARN")
    secret_name = os.environ.get("CREDENTIALS_SECRET_NAME")

    body = event if isinstance(event, dict) else {}
    symbols = body.get("symbols") or []
    if not symbols:
        # attempt auto-detection by scanning orders-history as specified in tasks.md
        # fetch credentials if available (env or secrets)
        api_key = os.environ.get("BITGET_API_KEY")
        secret_key = os.environ.get("BITGET_API_SECRET")
        passphrase = os.environ.get("BITGET_API_PASSPHRASE")
        if secret_name and (not api_key or not secret_key):
            creds = get_secret(secret_name, aws_region)
            api_key = api_key or creds.get("apiKey") or creds.get("api_key")
            secret_key = secret_key or creds.get("secretKey") or creds.get("secret_key")
            passphrase = passphrase or creds.get("passphrase")

        product_type = body.get("productType", "USDT-FUTURES")
        detected = _detect_symbols_by_scanning(api_key, secret_key, passphrase, product_type=product_type)
        symbols = detected
        # if still empty, return error per previous behavior
        if not symbols:
            return {"statusCode": 400, "body": json.dumps({"error": "symbols required and auto-detection found none"})}

    if not state_machine_arn:
        return {"statusCode": 500, "body": json.dumps({"error": "STATE_MACHINE_ARN not configured"})}

    # Build state machine input (symbols as list of strings per tasks.md)
    input_obj = {
        "startTimeMs": body.get("startTimeMs") or int(__import__("time").time() * 1000),
        "productType": body.get("productType", "USDT-FUTURES"),
        "symbols": symbols,
    }

    sf = boto3.client("stepfunctions", region_name=aws_region)
    try:
        res = sf.start_execution(stateMachineArn=state_machine_arn, input=json.dumps(input_obj))
        return {"statusCode": 202, "body": json.dumps({"executionArn": res.get("executionArn")})}
    except ClientError as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
