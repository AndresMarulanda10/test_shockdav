# Full local smoke test: coordinator -> mocked Step Functions -> workers -> aggregator
# This script mocks Bitget API, Step Functions, and S3 to exercise the full pipeline locally.
import sys
from pathlib import Path
import json
import os
from typing import Dict, Any

# Add repo root to sys.path
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

# Mocks storage for S3 keys
_mock_s3_store: Dict[str, Any] = {}

# Monkeypatch helpers
from src.lambdas.common import bitget_client
from src.lambdas.common import aws_helpers

# Fake Bitget: return small page then empty
async def fake_get_orders_async(api_key, secret_key, passphrase, symbol, params=None, timeout=20):
    if params and params.get('idLessThan'):
        return {'orders': []}
    return {'orders': [
        {'id': '3', 'orderId': '3', 'symbol': symbol, 'side': 'buy', 'price': '100', 'quantity': '0.1', 'status': 'filled', 'cTime': 1700000000000},
        {'id': '2', 'orderId': '2', 'symbol': symbol, 'side': 'sell', 'price': '110', 'quantity': '0.2', 'status': 'cancelled', 'cTime': 1700000001000},
        {'id': '1', 'orderId': '1', 'symbol': symbol, 'side': 'buy', 'price': '105', 'quantity': '0.05', 'status': 'filled', 'cTime': 1700000002000}
    ]}

bitget_client.get_orders_async = fake_get_orders_async

# Mock S3 helpers
def mock_upload_json_to_s3(bucket: str, key: str, data: Any):
    print(f"[mock_s3] upload to {bucket}/{key} (size={len(json.dumps(data))})")
    _mock_s3_store[f"{bucket}/{key}"] = data

def mock_read_json_from_s3(bucket: str, key: str):
    print(f"[mock_s3] read from {bucket}/{key}")
    return _mock_s3_store.get(f"{bucket}/{key}", {})

aws_helpers.upload_json_to_s3 = mock_upload_json_to_s3
aws_helpers.read_json_from_s3 = mock_read_json_from_s3

# Mock Step Functions: instead of starting executions, we'll synchronously call worker.handler for each symbol
from src.lambdas.coordinator.handler import handler as coordinator_handler
from src.lambdas.worker.app import handler as worker_handler
from src.lambdas.aggregator.handler import handler as aggregator_handler

# Monkeypatch boto3 client used by coordinator to avoid real AWS calls
import boto3
class FakeSFClient:
    def start_execution(self, stateMachineArn, input):
        print(f"[mock_sfn] start_execution called for {stateMachineArn} with input size={len(input)}")
        return {'executionArn': 'arn:local:execution:1'}

boto3.client = lambda *args, **kwargs: FakeSFClient()


def run_mock_step_function(symbols, startTimeMs, productType):
    per_symbol_results = []
    for s in symbols:
        symbol = s['symbol'] if isinstance(s, dict) and 'symbol' in s else s
        print(f"[mock_sfn] invoking worker for {symbol}")
        res = worker_handler({'symbol': symbol}, None)
        # worker returns either orders inline or s3_key
        if 's3_key' in res:
            per_symbol_results.append({'s3_key': res['s3_key']})
        else:
            per_symbol_results.append({'orders': res.get('orders', []), 'symbol': symbol})
    return per_symbol_results


if __name__ == '__main__':
    # configure envs used by handlers
    os.environ['RESULTS_BUCKET'] = 'mock-bucket'
    os.environ['RESULTS_PREFIX'] = 'bitget-orders/'
    os.environ['STATE_MACHINE_ARN'] = 'arn:local:statemachine'

    # Coordinator input: symbols list
    event = {'symbols': ['BTCUSDT', 'ETHUSDT'], 'startTimeMs': 1700000000000, 'productType': 'USDT-FUTURES'}

    print('[smoke] calling coordinator.handler')
    coord_resp = coordinator_handler(event, None)
    print('[smoke] coordinator returned:', coord_resp)

    # Simulate step functions invoking worker for each symbol
    per_symbol = run_mock_step_function([s for s in event['symbols']], event['startTimeMs'], event['productType'])

    print('[smoke] collected per-symbol results, calling aggregator...')
    agg_resp = aggregator_handler({'results': per_symbol}, None)
    print('[smoke] aggregator returned:', agg_resp)

    # show final object in mock s3
    final_key = agg_resp.get('final_key')
    if final_key:
        print('[smoke] final object in mock s3:')
        print(json.dumps(_mock_s3_store.get(f"mock-bucket/{final_key}"), indent=2))
    else:
        print('[smoke] no final key produced')
