"""Local Bitget extraction helper.

Scans for market symbols and probes multiple endpoint/parameter variants to
discover a working request shape for fetching user Futures orders. Results
are merged and written to the `artifacts/` directory.
"""

import os
import sys
import json
import time
import asyncio
from pathlib import Path
from typing import List, Dict, Any

import httpx

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

from src.lambdas.common import bitget_client
from src.lambdas.worker.app import handler as worker_handler

# Test credentials (from test.md)
API_KEY = 'bg_680026a00a63d58058c738c952ce67a2'
SECRET_KEY = '7abac4a9404e82830db5f9db5e867a8370c7e59dc74e52615c59552d0afbd7c9'
PASSPHRASE = '22Dominic22'

# Safety caps (can be overridden via environment)
MAX_PAGES = int(os.environ.get('MAX_DETECT_PAGES', '500'))
MAX_SCAN_ORDERS = int(os.environ.get('MAX_SCAN_ORDERS', '20000'))
MAX_SYMBOLS = int(os.environ.get('MAX_SYMBOLS', '200'))
MAX_PROBES_PER_SYMBOL = int(os.environ.get('MAX_PROBES_PER_SYMBOL', '24'))

ARTIFACTS_DIR = Path('artifacts')
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def extract_symbols_by_scanning(limit: int = 100) -> List[str]:
    """Scan orders-history (no symbol) and collect unique symbols.

    Uses idLessThan pagination. Stops when no more pages or caps reached.
    """
    print(f"Starting symbol detection (limit={limit}, max_pages={MAX_PAGES}, max_scan_orders={MAX_SCAN_ORDERS})")
    symbols = set()
    pages = 0
    scanned = 0
    id_less_than = None

    while True:
        pages += 1
        if pages > MAX_PAGES:
            print("Reached max pages cap during symbol detection")
            break

        params = {"limit": limit}
        if id_less_than:
            params['idLessThan'] = id_less_than

        try:
            resp = asyncio.run(
                bitget_client.get_orders_async(API_KEY, SECRET_KEY, PASSPHRASE, symbol='', params=params)
            )
        except (httpx.HTTPError, RuntimeError) as e:
            print(f"Error calling Bitget during detection: {e}")
            break

        page = resp.get('data') or resp.get('orders') or []
        if isinstance(page, dict) and 'orders' in page:
            page = page.get('orders')

        if not page:
            print('No more pages returned during detection')
            break

        for item in page:
            if not item or not isinstance(item, dict):
                continue
            item_sym = item.get('symbol') or item.get('symbolName') or item.get('instrument_id')
            if item_sym:
                symbols.add(item_sym)
        scanned += len(page)
        print(f"Detected page {pages}: fetched {len(page)} orders (total scanned {scanned}), unique symbols {len(symbols)}")

        # compute next idLessThan
        try:
            ids = [int(item.get('id') or item.get('orderId') or 0) for item in page if item]
            if not ids:
                break
            id_less_than = min(ids)
        except (TypeError, ValueError):
            break

        if scanned >= MAX_SCAN_ORDERS:
            print('Reached max scanned orders cap during detection')
            break

        # respect a small pause to be polite
        time.sleep(0.1)

    return sorted(symbols)


def fetch_market_symbols(cap: int = 200) -> List[str]:
    """Try public Bitget endpoints to list market symbols. Cap the number returned.

    If public endpoints fail, return a curated fallback list.
    """
    BASE = 'https://api.bitget.com'
    endpoints = [
        '/api/mix/v1/market/contracts',
        '/api/spot/v1/public/products',
        '/api/mix/v1/market/products',
    ]

    symbols = []
    for ep in endpoints:
        url = BASE + ep
        try:
            r = httpx.get(url, timeout=10)
            if r.status_code != 200:
                continue
            data = r.json()
            # traverse to extract symbol-like fields
            candidates = []
            if isinstance(data, dict):
                # common patterns: data['data'] or data['result'] or directly a list
                if 'data' in data and isinstance(data['data'], list):
                    candidates = data['data']
                elif 'result' in data and isinstance(data['result'], list):
                    candidates = data['result']
                elif isinstance(data.get('data'), dict):
                    # sometimes nested
                    for v in data['data'].values():
                        if isinstance(v, list):
                            candidates.extend(v)
                elif isinstance(data, list):
                    candidates = data
            elif isinstance(data, list):
                candidates = data

            for item in candidates:
                if not isinstance(item, dict):
                    continue
                sym_val = item.get('symbol') or item.get('contract') or item.get('instId') or item.get('symbolName')
                if sym_val and isinstance(sym_val, str) and sym_val.endswith('USDT'):
                    symbols.append(sym_val)

            if symbols:
                # dedupe and cap
                seen = []
                for s in symbols:
                    if s not in seen:
                        seen.append(s)
                    if len(seen) >= cap:
                        break
                return seen
        except (httpx.RequestError, ValueError):
            continue

    # Fallback curated list
    fallback = [
        'BTCUSDT','ETHUSDT','LTCUSDT','XRPUSDT','DOGEUSDT','BCHUSDT','ADAUSDT','SOLUSDT','DOTUSDT','LINKUSDT'
    ]
    return fallback[:cap]


def probe_symbol_for_orders(api_key: str, secret_key: str, passphrase: str, symbol: str, probes_cap: int = 6) -> bool:
    """Try several endpoint and param variations to detect whether the user has orders for `symbol`.

    Returns True if any probe returns orders (non-empty page). Treats HTTP 400 as a param shape mismatch and continues.
    """
    import itertools

    # endpoint templates to try (request_path), some Bitget variants
    # Expanded list of endpoint variants observed across Bitget docs and api surfaces
    endpoint_templates = [
        '/api/v2/mix/order/orders-history',
        '/api/mix/order/orders-history',
        '/api/mix/v1/order/orders-history',
        '/api/mix/v1/market/products',
        '/api/mix/v1/order/list',
        '/api/swap/v3/orders',
        '/api/spot/v1/history/orders',
        '/api/spot/v1/orders',
        '/api/v1/order/history',
        '/api/v1/mix/order/orders',
    ]

    product_types = [None, 'UMCBL', 'SWAP', 'USDT-FUTURES', 'FUTURES', 'PERP']
    param_keys = ['symbol', 'instId', 'instrument_id', 'symbolName']
    timestamp_modes = [False, True]  # False => ms, True => seconds
    methods = ['GET', 'POST']

    tried = 0
    for rp in endpoint_templates:
        for pt in product_types:
            for pk in param_keys:
                for ts_mode in timestamp_modes:
                    if tried >= probes_cap:
                        return False
                    params = {'limit': 1}
                    if pt:
                        params['productType'] = pt
                    # include symbol under alternative param key name
                    params[pk] = symbol
                    for method in methods:
                        tried += 1
                        body = None
                        if method == 'POST':
                            body = {pk: symbol, 'limit': 1}
                            if pt:
                                body['productType'] = pt
                        try:
                            resp = asyncio.run(
                                bitget_client.get_orders_async(
                                    api_key,
                                    secret_key,
                                    passphrase,
                                    symbol=symbol,
                                    params=params,
                                    request_path=rp,
                                    use_seconds_timestamp=ts_mode,
                                    method=method,
                                    body=body,
                                )
                            )
                            page = resp.get('data') or resp.get('orders') or []
                            if isinstance(page, dict) and 'orders' in page:
                                page = page.get('orders')
                            if page:
                                return True
                        except (httpx.HTTPError, RuntimeError) as e:
                            print(f'    probe variant failed (rp={rp},pt={pt},pk={pk},sec_ts={ts_mode},method={method}): {e}')
                        time.sleep(0.12)
    return False


def merge_and_write(all_results: List[Dict[str, Any]]) -> Path:
    """Merge orders from per-symbol results, sort by timestamp, and write JSON to artifacts."""
    all_orders: List[Dict[str, Any]] = []

    for r in all_results:
        if 'orders' in r and isinstance(r['orders'], list):
            all_orders.extend(r['orders'])
        elif 's3_key' in r:
            # not supported in local run
            continue

    def _order_time(o: Dict[str, Any]) -> int:
        for f in ("cTime", "orderTime", "timestamp", "time", "createdAt"):
            v = o.get(f)
            if v:
                try:
                    return int(v)
                except Exception:
                    try:
                        import dateutil.parser
                        dt = dateutil.parser.parse(v)
                        return int(dt.timestamp() * 1000)
                    except (ValueError, TypeError):
                        continue
        return 0

    all_orders.sort(key=_order_time)

    final_obj = {
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'orders': all_orders,
        'count': len(all_orders)
    }

    ts = int(time.time())
    out_path = ARTIFACTS_DIR / f'bitget-orders-{ts}-orders.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(final_obj, f, ensure_ascii=False)
    return out_path


if __name__ == '__main__':
    start_time = time.time()

    # set envs used by worker.handler
    os.environ['BITGET_API_KEY'] = API_KEY
    os.environ['BITGET_API_SECRET'] = SECRET_KEY
    os.environ['BITGET_API_PASSPHRASE'] = PASSPHRASE

    # Option 2: fetch market symbols and probe each symbol for user orders
    market_symbols = fetch_market_symbols(cap=MAX_SYMBOLS)
    print(f'Fetched {len(market_symbols)} market symbols (cap {MAX_SYMBOLS})')

    # Allow a curated-symbols shortcut so we can run extraction without probing.
    curated_env = os.environ.get('CURATED_SYMBOLS')
    force_curated = os.environ.get('FORCE_CURATED', '').lower() in ('1', 'true', 'yes')

    if curated_env:
        detected_symbols = [s.strip() for s in curated_env.split(',') if s.strip()]
        print(f'Using curated symbols from CURATED_SYMBOLS: {detected_symbols}')
    elif force_curated:
        # use the fetched market symbols as the curated set (cap enforced)
        detected_symbols = market_symbols[:MAX_SYMBOLS]
        print(f'FORCE_CURATED set — using first {len(detected_symbols)} market symbols as detected: {detected_symbols}')
    else:
        detected_symbols = []
        print('Probing symbols to detect user orders (this may take a while)')
        for i, sym in enumerate(market_symbols, 1):
            print(f'  Probing {i}/{len(market_symbols)}: {sym}')
            try:
                ok = probe_symbol_for_orders(API_KEY, SECRET_KEY, PASSPHRASE, sym, probes_cap=MAX_PROBES_PER_SYMBOL)
                if ok:
                    detected_symbols.append(sym)
                    print(f'    -> user has orders for {sym}')
            except Exception as e:
                print(f'    probe error for {sym}: {e}')

            # throttle probes
            time.sleep(0.8)

    print('Symbols detected via probing:', detected_symbols)

    if not detected_symbols:
        print('No symbols with user orders detected; aborting')
        sys.exit(1)

    all_results = []
    for idx, s in enumerate(detected_symbols, 1):
        print(f"\nExtracting symbol {idx}/{len(detected_symbols)}: {s}")
        try:
            res = worker_handler({'symbol': s}, None)
            print(f"  -> got {res.get('count') or len(res.get('orders', []))} orders for {s}")
            all_results.append(res)
        except Exception as e:
            print(f"  Error extracting {s}: {e}")

    out_path = merge_and_write(all_results)
    elapsed = time.time() - start_time
    print('\nExtraction finished')
    print('Total symbols processed:', len(all_results))
    total_orders = sum((r.get('count') or len(r.get('orders', []))) for r in all_results)
    print('Total orders:', total_orders)
    print('Elapsed seconds:', round(elapsed, 2))
    print('Final JSON saved to:', out_path)
