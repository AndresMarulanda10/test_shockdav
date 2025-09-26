# Integration local test: call FastAPI /start then simulate Step Functions -> workers -> aggregator -> call /download
from pathlib import Path
import sys
import os
import json

# ensure repo imports work
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

# Ensure environment variables used by lambdas are set before importing modules
os.environ['RESULTS_BUCKET'] = 'mock-bucket'
os.environ['RESULTS_PREFIX'] = 'bitget-orders/'
os.environ['STATE_MACHINE_ARN'] = 'arn:local:statemachine'

# Simple in-memory mock s3 store
_mock_s3_store = {}

# Monkeypatch bitget client and aws_helpers
from src.lambdas.common import bitget_client, aws_helpers

async def fake_get_orders_async(api_key, secret_key, passphrase, symbol, params=None, timeout=20):
    # simple behavior: one page then empty
    if params and params.get('idLessThan'):
        return {'orders': []}
    return {'orders': [
        {'id': '10', 'orderId': '10', 'symbol': symbol, 'side': 'buy', 'price': '100', 'quantity': '0.1', 'status': 'filled', 'cTime': 1700000000000},
        {'id': '9', 'orderId': '9', 'symbol': symbol, 'side': 'sell', 'price': '110', 'quantity': '0.2', 'status': 'cancelled', 'cTime': 1700000001000}
    ]}

bitget_client.get_orders_async = fake_get_orders_async

# Mock aws_helpers to store/read from _mock_s3_store
def mock_upload_json_to_s3(bucket, key, data):
    k = f"{bucket}/{key}"
    print(f"[mock_upload] {k}")
    _mock_s3_store[k] = data

def mock_read_json_from_s3(bucket, key):
    k = f"{bucket}/{key}"
    print(f"[mock_read] {k}")
    return _mock_s3_store.get(k, {})

aws_helpers.upload_json_to_s3 = mock_upload_json_to_s3
aws_helpers.read_json_from_s3 = mock_read_json_from_s3

# Fake boto3 client factory that returns different fake clients per service
import boto3
class FakeSFClient:
    def start_execution(self, stateMachineArn, input):
        print(f"[fake_sf] start_execution {stateMachineArn}")
        return {'executionArn': 'arn:local:execution:123'}
    def describe_execution(self, executionArn):
        return {'status': 'SUCCEEDED', 'output': json.dumps({'ok': True}), 'startDate': 'now'}

class FakeS3Client:
    def generate_presigned_url(self, ClientMethod, Params, ExpiresIn):
        # return a fake URL pointing to our in-memory store
        bucket = Params['Bucket']
        key = Params['Key']
        return f"https://mock-s3.local/{bucket}/{key}?expires_in={ExpiresIn}"

def fake_boto3_client(service_name, *args, **kwargs):
    if service_name == 'stepfunctions':
        return FakeSFClient()
    if service_name == 's3':
        return FakeS3Client()
    # other services not used
    return None

boto3.client = fake_boto3_client

# Now use FastAPI TestClient to call /start and /download
from fastapi.testclient import TestClient
from src.fastapi_app.main import app
from src.lambdas.worker.app import handler as worker_handler
from src.lambdas.aggregator.handler import handler as aggregator_handler

client = TestClient(app)

if __name__ == '__main__':
    os.environ['RESULTS_BUCKET'] = 'mock-bucket'
    os.environ['RESULTS_PREFIX'] = 'bitget-orders/'
    os.environ['STATE_MACHINE_ARN'] = 'arn:local:statemachine'

    payload = {'symbols': ['BTCUSDT', 'ETHUSDT']}

    print('[integration] POST /start')
    r = client.post('/start', json=payload)
    print('status', r.status_code, 'body', r.json())

    # Simulate Step Functions Map: call worker for each symbol and collect results
    per_symbol = []
    for sym in payload['symbols']:
        print(f"[integration] invoking worker for {sym}")
        res = worker_handler({'symbol': sym}, None)
        if 's3_key' in res:
            per_symbol.append({'s3_key': res['s3_key']})
        else:
            per_symbol.append({'orders': res.get('orders', []), 'symbol': sym})

    print('[integration] calling aggregator')
    agg = aggregator_handler({'results': per_symbol}, None)
    print('aggregator response', agg)

    # print stored keys in mock s3 for debugging
    print('[integration] keys in mock s3 store:')
    for k in _mock_s3_store.keys():
        print('  -', k)

    final_key = agg.get('final_key')
    print('[integration] GET /download?key=', final_key)
    resp = client.get('/download', params={'key': final_key})
    print('download response', resp.status_code, resp.json())

    # show the stored final object from our mock store
    stored = _mock_s3_store.get(f"mock-bucket/{final_key}")
    print('[integration] stored final object:')
    print(json.dumps(stored, indent=2))
