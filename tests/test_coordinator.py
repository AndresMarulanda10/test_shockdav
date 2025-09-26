import json
import os
from src.lambdas.coordinator.handler import handler


def test_handler_no_symbols():
    event = {}
    context = None
    response = handler(event, context)
    assert response["statusCode"] == 400
    assert json.loads(response["body"])["error"] == "symbols required"


def test_handler_missing_state_machine():
    # If STATE_MACHINE_ARN not configured, coordinator returns 500
    os.environ.pop("STATE_MACHINE_ARN", None)
    response = handler({"symbols": ["BTCUSDT"]}, None)
    assert response["statusCode"] == 500
