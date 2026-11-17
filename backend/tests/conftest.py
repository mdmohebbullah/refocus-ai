import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("OPENAI_API_KEY", "")  # tests use the deterministic placeholder provider

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import db as dbmod  # noqa: E402
from app.db import Base, make_engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def engine(tmp_path):
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path}/test.db"
    eng = make_engine(url)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def SessionTest(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def client(SessionTest, monkeypatch):
    def _get_db():
        s = SessionTest()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[dbmod.get_db] = _get_db
    monkeypatch.setattr(dbmod, "SessionLocal", SessionTest)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _register(client, email="maya@example.edu", name="Maya"):
    r = client.post("/api/auth/register", json={"email": email, "name": name, "password": "correct-horse-1"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def auth(client):
    return _register(client)


@pytest.fixture()
def other_auth(client):
    return _register(client, "lee@example.edu", "Dr. Lee")


@pytest.fixture()
def project(client, auth):
    r = client.post("/api/projects", headers=auth, json={"name": "Literature review: trust in XAI", "category": "literature_review",
                                                          "goal": "Compare how Study A and Study B measured user trust"})
    assert r.status_code == 201
    p = client.get(f"/api/projects/{r.json()['id']}", headers=auth).json()
    return p


PARA = "However, Study A and Study B differed in their measurement of user trust because"


def write_doc(client, auth, doc_id, text=None):
    text = text or f"Explainable AI is often assumed to increase trust. Study A used a self-report scale. {PARA}"
    r = client.patch(f"/api/documents/{doc_id}", headers=auth, json={"content_text": text,
                     "content_json": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]},
                     "cursor_pos": len(text)})
    assert r.status_code == 200, r.text
    return text
