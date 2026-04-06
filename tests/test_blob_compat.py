import io
import pathlib
import sys

import pytest
from flask.sessions import SecureCookieSessionInterface

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app as app_module


class FakeCursor:
    def __init__(self, fetchone_rows=None):
        self.fetchone_rows = list(fetchone_rows or [])
        self.execute_calls = []

    def execute(self, query, params=None):
        self.execute_calls.append((query, params))

    def fetchone(self):
        if self.fetchone_rows:
            return self.fetchone_rows.pop(0)
        return None


class FakeDB:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


class FakeContainer:
    def __init__(self):
        self.upload_calls = []

    def upload_blob(self, *args, **kwargs):
        self.upload_calls.append((args, kwargs))


class FailingContainer:
    def upload_blob(self, *args, **kwargs):
        raise RuntimeError("upload failed")


@pytest.fixture
def client(monkeypatch):
    app = app_module.app
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    app.session_interface = SecureCookieSessionInterface()
    return app.test_client()


def test_image_url_prefers_blob_url(monkeypatch):
    monkeypatch.setattr(app_module, "get_blob_url", lambda key: f"https://blob/{key}")
    post = {"id": 10, "mime": "image/jpeg", "img_blob_key": "abc.jpg"}
    assert app_module.image_url(post) == "https://blob/abc.jpg"


def test_image_url_falls_back_to_local_image_path(monkeypatch):
    monkeypatch.setattr(app_module, "get_blob_url", lambda key: None)
    post = {"id": 11, "mime": "image/png", "img_blob_key": "abc.png"}
    assert app_module.image_url(post) == "/image/11.png"


def test_post_index_uses_blob_when_container_is_available(client, monkeypatch):
    fake_container = FakeContainer()
    fake_cursor = FakeCursor(fetchone_rows=[{"id": 123}])
    fake_db = FakeDB(fake_cursor)

    monkeypatch.setattr(app_module, "get_session_user", lambda: {"id": 1})
    monkeypatch.setattr(app_module, "blob_container_client", lambda: fake_container)
    monkeypatch.setattr(app_module, "db", lambda: fake_db)

    with client.session_transaction() as sess:
        sess["csrf_token"] = "token"

    data = {
        "csrf_token": "token",
        "body": "hello",
        "file": (io.BytesIO(b"blob-data"), "a.jpg", "image/jpeg"),
    }
    resp = client.post("/", data=data, content_type="multipart/form-data")

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/posts/123")
    assert len(fake_container.upload_calls) == 1

    query, params = fake_cursor.execute_calls[0]
    assert "img_blob_key" in query
    assert params[2] == b""
    assert params[4].endswith(".jpg")


def test_post_index_uses_imgdata_when_container_is_not_available(client, monkeypatch):
    fake_cursor = FakeCursor(fetchone_rows=[{"id": 456}])
    fake_db = FakeDB(fake_cursor)

    monkeypatch.setattr(app_module, "get_session_user", lambda: {"id": 1})
    monkeypatch.setattr(app_module, "blob_container_client", lambda: None)
    monkeypatch.setattr(app_module, "db", lambda: fake_db)

    with client.session_transaction() as sess:
        sess["csrf_token"] = "token"

    raw = b"legacy-img"
    data = {
        "csrf_token": "token",
        "body": "legacy",
        "file": (io.BytesIO(raw), "a.png", "image/png"),
    }
    resp = client.post("/", data=data, content_type="multipart/form-data")

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/posts/456")

    query, params = fake_cursor.execute_calls[0]
    assert "img_blob_key" not in query
    assert params[2] == raw


def test_post_index_falls_back_to_imgdata_when_blob_upload_fails(client, monkeypatch):
    fake_cursor = FakeCursor(fetchone_rows=[{"id": 789}])
    fake_db = FakeDB(fake_cursor)

    monkeypatch.setattr(app_module, "get_session_user", lambda: {"id": 1})
    monkeypatch.setattr(app_module, "blob_container_client", lambda: FailingContainer())
    monkeypatch.setattr(app_module, "db", lambda: fake_db)

    with client.session_transaction() as sess:
        sess["csrf_token"] = "token"

    raw = b"fallback-img"
    data = {
        "csrf_token": "token",
        "body": "fallback",
        "file": (io.BytesIO(raw), "a.png", "image/png"),
    }
    resp = client.post("/", data=data, content_type="multipart/form-data")

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/posts/789")

    query, params = fake_cursor.execute_calls[0]
    assert "img_blob_key" not in query
    assert params[2] == raw


def test_get_image_redirects_to_blob_when_blob_key_exists(client, monkeypatch):
    fake_cursor = FakeCursor(
        fetchone_rows=[
            {
                "id": 1,
                "mime": "image/jpeg",
                "img_blob_key": "k.jpg",
                "imgdata": b"old",
            }
        ]
    )
    fake_db = FakeDB(fake_cursor)

    monkeypatch.setattr(app_module, "db", lambda: fake_db)
    monkeypatch.setattr(
        app_module, "get_blob_url", lambda key: "https://example.blob.core.windows.net/images/k.jpg"
    )

    resp = client.get("/image/1.jpg")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://example.blob.core.windows.net/images/k.jpg"


def test_get_image_returns_imgdata_when_blob_key_is_missing(client, monkeypatch):
    fake_cursor = FakeCursor(
        fetchone_rows=[
            {
                "id": 2,
                "mime": "image/gif",
                "img_blob_key": None,
                "imgdata": b"gif-bytes",
            }
        ]
    )
    fake_db = FakeDB(fake_cursor)

    monkeypatch.setattr(app_module, "db", lambda: fake_db)

    resp = client.get("/image/2.gif")
    assert resp.status_code == 200
    assert resp.mimetype == "image/gif"
    assert resp.data == b"gif-bytes"
