"""Tests for settings, /health and frontend serving (milestone M0)."""

import pytest
from fastapi.testclient import TestClient

from app import config, main

ENV_NAMES = [
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "GEMINI_FALLBACK_MODEL",
    "GEMINI_TTS_MODEL",
    "NESSIE_BASE_URL",
    "NESSIE_API_KEY",
    "NESSIE_CUSTOMER_ID",
    "NESSIE_ACCOUNT_ID",
    "SEED_BALANCE_CENTS",
    "MONGODB_URI",
    "DEMO_OFFLINE",
    "TOKEN_SECRET",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """Start every test with no settings in the environment and no .env file."""
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / "no-such.env")
    monkeypatch.setattr(main, "FRONTEND_DIST", tmp_path / "no-such-dist")


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture
def dist(monkeypatch, tmp_path):
    """A tiny fake frontend build."""
    folder = tmp_path / "dist"
    (folder / "assets").mkdir(parents=True)
    (folder / "index.html").write_text("<html>guarded app</html>")
    (folder / "assets" / "app.js").write_text("console.log('hi')")
    (tmp_path / "outside.txt").write_text("not part of the build")
    monkeypatch.setattr(main, "FRONTEND_DIST", folder)
    return folder


# --- settings ---------------------------------------------------------------


def test_settings_defaults():
    s = config.get_settings()
    assert s.gemini_model == "gemini-3.8-flash"
    assert s.gemini_fallback_model == "gemini-3.5-flash-lite"
    assert s.gemini_tts_model == "gemini-3.8-flash-tts"
    assert s.nessie_base_url == "https://api.nessieisreal.com"
    assert s.seed_balance_cents == 200000
    assert s.demo_offline is False
    for field in ("gemini_api_key", "nessie_api_key", "nessie_customer_id",
                  "nessie_account_id", "mongodb_uri", "token_secret"):
        assert getattr(s, field) == ""


def test_repo_paths():
    assert (config.REPO_ROOT / "backend" / "app" / "config.py").is_file()
    assert config.REPO_ROOT / ".env" == config.REPO_ROOT.joinpath(".env")


@pytest.mark.parametrize(
    "value, expected",
    [("1", True), ("true", True), ("TRUE", True), (" true ", True),
     ("0", False), ("false", False), ("", False), ("nope", False)],
)
def test_demo_offline_parsing(monkeypatch, value, expected):
    monkeypatch.setenv("DEMO_OFFLINE", value)
    assert config.get_settings().demo_offline is expected


def test_settings_read_env_on_each_call(monkeypatch):
    monkeypatch.setenv("SEED_BALANCE_CENTS", "12345")
    assert config.get_settings().seed_balance_cents == 12345
    monkeypatch.setenv("SEED_BALANCE_CENTS", "500")
    assert config.get_settings().seed_balance_cents == 500


def test_bad_seed_balance_is_a_clear_error(monkeypatch):
    monkeypatch.setenv("SEED_BALANCE_CENTS", "lots")
    with pytest.raises(ValueError, match="SEED_BALANCE_CENTS"):
        config.get_settings()


def test_dotenv_is_loaded_but_does_not_override_environment(monkeypatch, tmp_path):
    env_file = tmp_path / "test.env"
    env_file.write_text("NESSIE_ACCOUNT_ID=from-file\nNESSIE_CUSTOMER_ID=from-file\n")
    monkeypatch.setattr(config, "ENV_PATH", env_file)
    monkeypatch.setenv("NESSIE_ACCOUNT_ID", "from-environment")
    try:
        s = config.get_settings()
        assert s.nessie_account_id == "from-environment"
        assert s.nessie_customer_id == "from-file"
    finally:
        # load_dotenv wrote this one into os.environ itself; tidy it up.
        monkeypatch.delenv("NESSIE_CUSTOMER_ID", raising=False)


# --- /health ----------------------------------------------------------------


def test_health_shape(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "demo_offline", "nessie_configured", "gemini_configured"}
    assert body["status"] == "ok"
    for key in ("demo_offline", "nessie_configured", "gemini_configured"):
        assert isinstance(body[key], bool)
    assert body == {"status": "ok", "demo_offline": False,
                    "nessie_configured": False, "gemini_configured": False}


def test_health_does_not_leak_secrets(client, monkeypatch):
    secrets = {
        "GEMINI_API_KEY": "gem-secret-AAA111",
        "NESSIE_API_KEY": "nessie-secret-BBB222",
        "TOKEN_SECRET": "token-secret-CCC333",
        "NESSIE_ACCOUNT_ID": "acct-DDD444",
        "MONGODB_URI": "mongodb://user:pw-EEE555@example.invalid/db",
    }
    for name, value in secrets.items():
        monkeypatch.setenv(name, value)
    response = client.get("/health")
    body = response.json()
    assert body["gemini_configured"] is True
    assert body["nessie_configured"] is True
    for value in secrets.values():
        assert value not in response.text


def test_nessie_needs_both_key_and_account(client, monkeypatch):
    monkeypatch.setenv("NESSIE_API_KEY", "some-key")
    assert client.get("/health").json()["nessie_configured"] is False
    monkeypatch.setenv("NESSIE_ACCOUNT_ID", "some-account")
    assert client.get("/health").json()["nessie_configured"] is True


def test_demo_offline_counts_as_nessie_configured(client, monkeypatch):
    monkeypatch.setenv("DEMO_OFFLINE", "1")
    body = client.get("/health").json()
    assert body["demo_offline"] is True
    assert body["nessie_configured"] is True
    assert body["gemini_configured"] is False


# --- frontend serving ---------------------------------------------------------


def test_root_works_without_frontend_build(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "npm run build" in response.text


def test_unknown_path_without_frontend_build_is_404(client):
    assert client.get("/some/page").status_code == 404


def test_frontend_is_served_when_built(client, dist):
    assert "guarded app" in client.get("/").text
    assert "console.log" in client.get("/assets/app.js").text
    # Unknown non-API path falls back to index.html so the SPA can route it.
    response = client.get("/letter/123")
    assert response.status_code == 200
    assert "guarded app" in response.text


def test_frontend_does_not_shadow_api_paths(client, dist):
    assert client.get("/health").json()["status"] == "ok"
    for path in ("/letters", "/proposals/abc", "/account", "/audit", "/health/x"):
        response = client.get(path)
        # 405 is fine too: /letters exists but only accepts POST.
        assert response.status_code in (404, 405), path
        assert "guarded app" not in response.text
    # Non-GET requests never get the frontend either.
    assert client.post("/some/page").status_code in (404, 405)


def test_frontend_cannot_serve_files_outside_dist(client, dist):
    for path in ("/../outside.txt", "/%2e%2e/outside.txt", "/assets/../../outside.txt"):
        assert "not part of the build" not in client.get(path).text
