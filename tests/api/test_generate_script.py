"""Tests for practice script generation endpoint."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from .conftest import csrf_headers, register


def test_generate_script_endpoint(app: FastAPI) -> None:
    client = TestClient(app, base_url="http://testserver")
    user_headers = csrf_headers(register(client))

    # Must be signed in
    unauth = client.post("/api/generate-script", headers={"X-Requested-With": "SpeechArena"})
    assert unauth.status_code in (401, 403)

    # Authenticated user should receive an instant practice passage
    res = client.post("/api/generate-script", headers=user_headers)
    assert res.status_code == 200
    data = res.json()
    assert "transcript" in data
    assert isinstance(data["transcript"], str)
    assert len(data["transcript"]) > 20
    assert data["transcript"].endswith((".", "!", "?"))
