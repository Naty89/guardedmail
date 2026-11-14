"""Shared test setup: the audit log always writes to a temporary folder."""

import pytest

from app import audit, config


@pytest.fixture(autouse=True)
def audit_in_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(audit, "DATA_DIR", tmp_path / "audit-data")
    monkeypatch.delenv("MONGODB_URI", raising=False)
    # Never read the developer's real .env from a test.
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / "no-such.env")
    audit.reset_log()
    yield
    audit.reset_log()
