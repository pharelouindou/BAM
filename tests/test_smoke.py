"""Tests smoke BAM — pytest tests/test_smoke.py"""
import os

import pytest
from fastapi.testclient import TestClient

# Skip API tests si pas de DATABASE_URL (CI sans secrets)
needs_db = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL requise",
)


@pytest.fixture
def client():
    from api.app import app

    return TestClient(app)


@needs_db
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["db"] == "ok"


@needs_db
def test_departements(client):
    r = client.get("/departements")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@needs_db
def test_grille_stats(client):
    r = client.get("/grille/stats")
    assert r.status_code == 200
    data = r.json()
    assert "total_points" in data or isinstance(data, list)


def test_import_pipeline():
    from bam_pipeline import DEPTS, collecte_bam

    assert len(DEPTS) == 12
    assert callable(collecte_bam)
