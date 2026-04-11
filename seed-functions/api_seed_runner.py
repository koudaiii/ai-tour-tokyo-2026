from __future__ import annotations

import json
import mimetypes
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from http.cookiejar import CookieJar
from pathlib import Path

# Seed account name configuration
# Uses "_" separator (hyphen is rejected by validate_user regex [0-9a-zA-Z_]{3,})
SEED_RUN_ID_LENGTH = 8


def generate_run_id() -> str:
    return uuid.uuid4().hex[:SEED_RUN_ID_LENGTH]


def make_seed_account_name(base_name: str, run_id: str) -> str:
    return f"{base_name}_{run_id}"


_CSRF_TOKEN_RE = re.compile(r'name="csrf_token"\s+value="([^"]+)"')


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def extract_images(images_zip: Path, extract_dir: Path) -> list[Path]:
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(images_zip) as zf:
        zf.extractall(extract_dir)

    return sorted(
        p
        for p in extract_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif"}
    )


def extract_csrf_token(html: str) -> str:
    match = _CSRF_TOKEN_RE.search(html)
    if not match:
        raise ValueError("csrf_token not found in HTML response")
    return match.group(1)


def encode_multipart_formdata(
    fields: dict[str, str],
    file_field: str,
    filename: str,
    file_bytes: bytes,
    mime: str,
) -> tuple[bytes, str]:
    boundary = f"----seed-boundary-{uuid.uuid4().hex}"
    parts: list[bytes] = []

    for name, value in fields.items():
        parts.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(
                    "utf-8"
                ),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )

    parts.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{file_field}"; '
                f'filename="{filename}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {mime}\r\n\r\n".encode("utf-8"),
            file_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )

    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class ApiSession:
    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.cookie_jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        data: bytes | None = None,
    ) -> tuple[int, bytes, dict[str, str]]:
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
        )
        for key, value in (headers or {}).items():
            req.add_header(key, value)

        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                return resp.getcode(), resp.read(), dict(resp.headers.items())
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed: {e.code} {detail}") from e

    def submit_form(self, path: str, form: dict[str, str]) -> tuple[int, bytes, dict[str, str]]:
        body = urllib.parse.urlencode(form).encode("utf-8")
        return self.request(
            path,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=body,
        )

    def register_and_login(self, account_name: str, password: str) -> str:
        self.submit_form(
            "/register",
            {"account_name": account_name, "password": password},
        )
        self.submit_form(
            "/login",
            {"account_name": account_name, "password": password},
        )
        _, html, _ = self.request("/")
        return extract_csrf_token(html.decode("utf-8", errors="replace"))

    def create_post(self, body: str, image_path: Path, csrf_token: str) -> int:
        mime = mimetypes.guess_type(str(image_path))[0]
        if mime not in ("image/jpeg", "image/png", "image/gif"):
            raise ValueError(f"Unsupported image mime: {image_path} ({mime})")

        payload, content_type = encode_multipart_formdata(
            {
                "body": body,
                "csrf_token": csrf_token,
            },
            file_field="file",
            filename=image_path.name,
            file_bytes=image_path.read_bytes(),
            mime=mime,
        )
        _, raw, _ = self.request(
            "/api/posts",
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": content_type,
            },
            data=payload,
        )
        response = json.loads(raw.decode("utf-8"))
        return int(response["id"])


def run_seed_via_api(
    api_base_url: str,
    users_json: Path,
    posts_json: Path,
    images_zip: Path,
    extract_dir: Path,
    post_count: int,
    run_id: str | None = None,
    log=print,
) -> int:
    if not api_base_url:
        raise ValueError("API base URL is required")
    if post_count <= 0:
        raise ValueError("--post-count must be greater than 0")

    for path in (users_json, posts_json, images_zip):
        if not path.exists():
            raise FileNotFoundError(f"Required file not found: {path}")

    users_data = load_json(users_json)
    posts_data = load_json(posts_json)
    if not isinstance(users_data, list) or not users_data:
        raise ValueError(f"Invalid users JSON: {users_json}")
    if not isinstance(posts_data, list) or not posts_data:
        raise ValueError(f"Invalid posts JSON: {posts_json}")

    image_paths = extract_images(images_zip, extract_dir)
    if len(posts_data) < post_count:
        raise ValueError(
            f"Not enough post texts: need {post_count}, got {len(posts_data)}"
        )
    if len(image_paths) < post_count:
        raise ValueError(
            f"Not enough images: need {post_count}, got {len(image_paths)}"
        )

    if not run_id:
        run_id = generate_run_id()
    log(f"[seed] run_id: {run_id}")

    sessions: list[tuple[ApiSession, str, str]] = []
    for entry in users_data:
        account_name = make_seed_account_name(entry.get("account_name"), run_id)
        password = entry.get("password")
        if not account_name or not password:
            raise ValueError(
                f"Each user entry must have account_name/password: {entry}"
            )

        session = ApiSession(api_base_url)
        csrf_token = session.register_and_login(account_name, password)
        sessions.append((session, csrf_token, account_name))

    log(f"[seed] users ready through API: {len(sessions)}")

    created = 0
    for i in range(post_count):
        body = posts_data[i].get("body")
        if not body:
            raise ValueError(f"Post entry at index {i} has no body")

        session, csrf_token, account_name = sessions[i % len(sessions)]
        post_id = session.create_post(body, image_paths[i], csrf_token)
        created += 1
        log(f"[seed] created post {post_id} via API as {account_name}")

    return created
