from src.lambdas.common.bitget_client import sign_request


def test_sign_request_basic():
    sig = sign_request("secret", "12345", "GET", "/api/v2/test", "a=1", "")
    assert isinstance(sig, str)
    assert len(sig) > 0
