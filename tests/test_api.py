import datetime
import io
import json
import pathlib
import sys

import pytest
from flask.sessions import SecureCookieSessionInterface

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app as app_module

NOW = datetime.datetime(2025, 1, 15, 12, 0, 0)


def _make_user(id=1, account_id="alice", del_flg=0):
    return {
        "id": id,
        "account_id": account_id,
        "del_flg": del_flg,
        "authority": 0,
        "created_at": NOW,
    }


def _make_post(id=1, user_id=1, user=None):
    if user is None:
        user = _make_user(id=user_id)
    return {
        "id": id,
        "user_id": user_id,
        "body": f"post body {id}",
        "mime": "image/jpeg",
        "created_at": NOW,
        "user": user,
        "comment_count": 0,
        "comments": [],
    }


class FakeCursor:
    def __init__(self, results=None):
        self._results = list(results or [])
        self._iter_data = None
        self.execute_calls = []

    def execute(self, query, params=None):
        self.execute_calls.append((query, params))
        if self._results:
            self._current = self._results.pop(0)
        else:
            self._current = []
        self._iter_data = list(self._current) if isinstance(self._current, list) else [self._current]

    def fetchone(self):
        if self._iter_data:
            return self._iter_data[0]
        return None

    def fetchall(self):
        return list(self._iter_data) if self._iter_data else []

    def __iter__(self):
        return iter(self._iter_data or [])


class FakeDB:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


@pytest.fixture
def client(monkeypatch):
    app = app_module.app
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    app.session_interface = SecureCookieSessionInterface()
    return app.test_client()


# ---- POST /login ----


def test_post_login_uses_account_id_field(client, monkeypatch):
    captured = {}

    def fake_try_login(account_id, password):
        captured["account_id"] = account_id
        captured["password"] = password
        return {"id": 42}

    monkeypatch.setattr(app_module, "get_session_user", lambda: None)
    monkeypatch.setattr(app_module, "try_login", fake_try_login)

    resp = client.post(
        "/login",
        data={"account_id": "alice", "password": "secret123"},
    )

    assert resp.status_code == 302
    assert captured == {"account_id": "alice", "password": "secret123"}


# ---- POST /register ----


def test_post_register_uses_account_id_column(client, monkeypatch):
    fake_cursor = FakeCursor(results=[None, {"id": 123}])
    monkeypatch.setattr(app_module, "get_session_user", lambda: None)
    monkeypatch.setattr(app_module, "db", lambda: FakeDB(fake_cursor))

    resp = client.post(
        "/register",
        data={"account_id": "new_user", "password": "secret123"},
    )

    assert resp.status_code == 302
    assert "account_id" in fake_cursor.execute_calls[0][0]
    assert fake_cursor.execute_calls[0][1] == ("new_user",)
    assert "INSERT INTO users (account_id, passhash)" in fake_cursor.execute_calls[1][0]
    assert fake_cursor.execute_calls[1][1][0] == "new_user"


# ---- Serialization ----


def test_post_to_dict_uses_account_id_key(monkeypatch):
    post = _make_post()
    monkeypatch.setattr(app_module, "get_blob_url", lambda key: None)

    data = app_module._post_to_dict(post)

    assert "account_id" in data["user"]
    assert data["user"]["account_id"] == "alice"
    assert "account_name" not in data["user"]


# ---- GET /api/posts ----


def test_api_get_posts_returns_json(client, monkeypatch):
    post = _make_post()
    monkeypatch.setattr(app_module, "make_posts", lambda results, **kw: [post])
    monkeypatch.setattr(app_module, "get_blob_url", lambda key: None)

    fake_cursor = FakeCursor(results=[[]])
    monkeypatch.setattr(app_module, "db", lambda: FakeDB(fake_cursor))

    resp = client.get("/api/posts")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "posts" in data
    assert len(data["posts"]) == 1
    assert data["posts"][0]["id"] == 1
    assert data["posts"][0]["body"] == "post body 1"
    assert data["posts"][0]["image_url"] == "/image/1.jpg"


def test_api_get_posts_with_max_created_at(client, monkeypatch):
    monkeypatch.setattr(app_module, "make_posts", lambda results, **kw: [])
    monkeypatch.setattr(app_module, "get_blob_url", lambda key: None)

    fake_cursor = FakeCursor(results=[[]])
    monkeypatch.setattr(app_module, "db", lambda: FakeDB(fake_cursor))

    resp = client.get("/api/posts?max_created_at=2025-01-15T12:00:00")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["posts"] == []
    assert "created_at <=" in fake_cursor.execute_calls[0][0]


# ---- GET /api/posts/<id> ----


def test_api_get_post_found(client, monkeypatch):
    post = _make_post(id=42)
    monkeypatch.setattr(app_module, "make_posts", lambda results, **kw: [post])
    monkeypatch.setattr(app_module, "get_blob_url", lambda key: None)

    fake_cursor = FakeCursor(results=[[]])
    monkeypatch.setattr(app_module, "db", lambda: FakeDB(fake_cursor))

    resp = client.get("/api/posts/42")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["post"]["id"] == 42


def test_api_get_post_not_found(client, monkeypatch):
    monkeypatch.setattr(app_module, "make_posts", lambda results, **kw: [])

    fake_cursor = FakeCursor(results=[[]])
    monkeypatch.setattr(app_module, "db", lambda: FakeDB(fake_cursor))

    resp = client.get("/api/posts/9999")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "not found"


# ---- POST /api/posts ----


def test_api_create_post_requires_login(client, monkeypatch):
    monkeypatch.setattr(app_module, "get_session_user", lambda: None)

    resp = client.post("/api/posts")
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "login required"


def test_api_create_post_validates_csrf(client, monkeypatch):
    monkeypatch.setattr(app_module, "get_session_user", lambda: {"id": 1})

    with client.session_transaction() as sess:
        sess["csrf_token"] = "correct"

    data = {
        "csrf_token": "wrong",
        "body": "test",
        "file": (io.BytesIO(b"img"), "a.jpg", "image/jpeg"),
    }
    resp = client.post("/api/posts", data=data, content_type="multipart/form-data")
    assert resp.status_code == 422


def test_api_create_post_requires_file(client, monkeypatch):
    monkeypatch.setattr(app_module, "get_session_user", lambda: {"id": 1})

    with client.session_transaction() as sess:
        sess["csrf_token"] = "token"

    data = {"csrf_token": "token", "body": "no file"}
    resp = client.post("/api/posts", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "file is required"


def test_api_create_post_rejects_unsupported_mime(client, monkeypatch):
    monkeypatch.setattr(app_module, "get_session_user", lambda: {"id": 1})

    with client.session_transaction() as sess:
        sess["csrf_token"] = "token"

    data = {
        "csrf_token": "token",
        "body": "test",
        "file": (io.BytesIO(b"data"), "a.bmp", "image/bmp"),
    }
    resp = client.post("/api/posts", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "unsupported image format"


def test_api_create_post_success(client, monkeypatch):
    fake_cursor = FakeCursor(results=[[{"id": 100}]])
    monkeypatch.setattr(app_module, "get_session_user", lambda: {"id": 1})
    monkeypatch.setattr(app_module, "blob_container_client", lambda: None)
    monkeypatch.setattr(app_module, "db", lambda: FakeDB(fake_cursor))

    with client.session_transaction() as sess:
        sess["csrf_token"] = "token"

    data = {
        "csrf_token": "token",
        "body": "hello",
        "file": (io.BytesIO(b"img-data"), "a.jpg", "image/jpeg"),
    }
    resp = client.post("/api/posts", data=data, content_type="multipart/form-data")
    assert resp.status_code == 201
    assert resp.get_json()["id"] == 100


# ---- POST /api/comments ----


def test_api_create_comment_requires_login(client, monkeypatch):
    monkeypatch.setattr(app_module, "get_session_user", lambda: None)

    resp = client.post("/api/comments", json={"post_id": 1, "comment": "hi"})
    assert resp.status_code == 401


def test_api_create_comment_validates_csrf(client, monkeypatch):
    monkeypatch.setattr(app_module, "get_session_user", lambda: {"id": 1})

    with client.session_transaction() as sess:
        sess["csrf_token"] = "correct"

    resp = client.post(
        "/api/comments",
        json={"post_id": 1, "comment": "hi", "csrf_token": "wrong"},
    )
    assert resp.status_code == 422


def test_api_create_comment_validates_post_id(client, monkeypatch):
    monkeypatch.setattr(app_module, "get_session_user", lambda: {"id": 1})

    with client.session_transaction() as sess:
        sess["csrf_token"] = "token"

    resp = client.post(
        "/api/comments",
        json={"post_id": "abc", "comment": "hi", "csrf_token": "token"},
    )
    assert resp.status_code == 400


def test_api_create_comment_requires_comment(client, monkeypatch):
    monkeypatch.setattr(app_module, "get_session_user", lambda: {"id": 1})

    with client.session_transaction() as sess:
        sess["csrf_token"] = "token"

    resp = client.post(
        "/api/comments",
        json={"post_id": 1, "comment": "", "csrf_token": "token"},
    )
    assert resp.status_code == 400


def test_api_create_comment_success(client, monkeypatch):
    fake_cursor = FakeCursor()
    monkeypatch.setattr(app_module, "get_session_user", lambda: {"id": 1})
    monkeypatch.setattr(app_module, "db", lambda: FakeDB(fake_cursor))

    with client.session_transaction() as sess:
        sess["csrf_token"] = "token"

    resp = client.post(
        "/api/comments",
        json={"post_id": 5, "comment": "nice post", "csrf_token": "token"},
    )
    assert resp.status_code == 201
    assert resp.get_json()["post_id"] == 5


# ---- GET /api/users ----


def test_api_get_users(client, monkeypatch):
    users = [_make_user(id=1, account_id="alice"), _make_user(id=2, account_id="bob")]
    fake_cursor = FakeCursor(results=[users])
    monkeypatch.setattr(app_module, "db", lambda: FakeDB(fake_cursor))

    resp = client.get("/api/users")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["users"]) == 2
    assert data["users"][0]["account_id"] == "alice"
    assert data["users"][1]["account_id"] == "bob"


# ---- GET /api/users/<account_id> ----


def test_api_get_user_found(client, monkeypatch):
    user = _make_user(id=10, account_id="mary")
    monkeypatch.setattr(app_module, "_get_user_or_404", lambda name: user if name == "mary" else None)

    fake_cursor = FakeCursor(results=[
        [{"count": 5}],       # comment_count
        [{"id": 1}, {"id": 2}],  # post_ids
        [{"count": 3}],       # commented_count
    ])
    monkeypatch.setattr(app_module, "db", lambda: FakeDB(fake_cursor))

    resp = client.get("/api/users/mary")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["user"]["account_id"] == "mary"
    assert data["post_count"] == 2
    assert data["comment_count"] == 5
    assert data["commented_count"] == 3


def test_api_get_user_not_found(client, monkeypatch):
    monkeypatch.setattr(app_module, "_get_user_or_404", lambda name: None)

    resp = client.get("/api/users/nobody")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "not found"


# ---- GET /api/users/<account_id>/posts ----


def test_api_get_user_posts(client, monkeypatch):
    user = _make_user(id=10, account_id="mary")
    post = _make_post(id=1, user_id=10, user=user)
    monkeypatch.setattr(app_module, "_get_user_or_404", lambda name: user if name == "mary" else None)
    monkeypatch.setattr(app_module, "make_posts", lambda results, **kw: [post])
    monkeypatch.setattr(app_module, "get_blob_url", lambda key: None)

    fake_cursor = FakeCursor(results=[[]])
    monkeypatch.setattr(app_module, "db", lambda: FakeDB(fake_cursor))

    resp = client.get("/api/users/mary/posts")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["posts"]) == 1
    assert data["posts"][0]["user"]["account_id"] == "mary"


def test_api_get_user_posts_user_not_found(client, monkeypatch):
    monkeypatch.setattr(app_module, "_get_user_or_404", lambda name: None)

    resp = client.get("/api/users/nobody/posts")
    assert resp.status_code == 404


# ---- GET /api/users/<account_id>/posts/<id> ----


def test_api_get_user_post_found(client, monkeypatch):
    user = _make_user(id=10, account_id="mary")
    post = _make_post(id=7, user_id=10, user=user)
    monkeypatch.setattr(app_module, "_get_user_or_404", lambda name: user if name == "mary" else None)
    monkeypatch.setattr(app_module, "make_posts", lambda results, **kw: [post])
    monkeypatch.setattr(app_module, "get_blob_url", lambda key: None)

    fake_cursor = FakeCursor(results=[[]])
    monkeypatch.setattr(app_module, "db", lambda: FakeDB(fake_cursor))

    resp = client.get("/api/users/mary/posts/7")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["post"]["id"] == 7


def test_api_get_user_post_not_found(client, monkeypatch):
    user = _make_user(id=10, account_id="mary")
    monkeypatch.setattr(app_module, "_get_user_or_404", lambda name: user if name == "mary" else None)
    monkeypatch.setattr(app_module, "make_posts", lambda results, **kw: [])

    fake_cursor = FakeCursor(results=[[]])
    monkeypatch.setattr(app_module, "db", lambda: FakeDB(fake_cursor))

    resp = client.get("/api/users/mary/posts/9999")
    assert resp.status_code == 404


def test_api_get_user_post_user_not_found(client, monkeypatch):
    monkeypatch.setattr(app_module, "_get_user_or_404", lambda name: None)

    resp = client.get("/api/users/nobody/posts/1")
    assert resp.status_code == 404
