# Local smoke runner for worker handler
# This script mocks src.lambdas.common.bitget_client.get_orders_async
# and invokes the worker.handler to verify flow without real API calls.
import sys
from pathlib import Path
import json

# Add repo root to sys.path so `src` is importable
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

# Monkeypatch the async client
from src.lambdas.common import bitget_client

async def fake_get_orders_async(api_key, secret_key, passphrase, symbol, params=None, timeout=20):
    # simulate two pages: first with 3 orders, second empty
    # Use idLessThan to control behavior
    if params and params.get('idLessThan'):
        return {'orders': []}
    else:
        return {'orders': [
            {'id': '300', 'orderId': '300', 'symbol': symbol, 'side': 'buy', 'price': '100', 'quantity': '0.1', 'status': 'filled', 'cTime': 1700000000000},
            {'id': '200', 'orderId': '200', 'symbol': symbol, 'side': 'sell', 'price': '110', 'quantity': '0.2', 'status': 'cancelled', 'cTime': 1700000001000},
            {'id': '100', 'orderId': '100', 'symbol': symbol, 'side': 'buy', 'price': '105', 'quantity': '0.05', 'status': 'filled', 'cTime': 1700000002000}
        ]}

# replace the real function
bitget_client.get_orders_async = fake_get_orders_async

# import handler after monkeypatch to ensure it picks up patched function
from src.lambdas.worker.app import handler as worker_handler

if __name__ == '__main__':
    print('Invoking worker.handler with mocked Bitget client...')
    out = worker_handler({'symbol': 'BTCUSDT'}, None)
    print('Result:')
    print(json.dumps(out, indent=2))
