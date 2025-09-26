import pytest
from src.fastapi_app.main import app


def test_app_is_fastapi():
    assert hasattr(app, "router")
    assert hasattr(app, "add_middleware")

# Additional tests can be added here
