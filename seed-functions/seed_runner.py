from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import uuid
import zipfile
from pathlib import Path

import psycopg2
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings


_blob_service_client = None

# Seed account name configuration
# Uses "_" separator (hyphen is rejected by validate_user regex [0-9a-zA-Z_]{3,})
SEED_RUN_ID_LENGTH = 8


def generate_run_id() -> str:
    return uuid.uuid4().hex[:SEED_RUN_ID_LENGTH]


def make_seed_account_name(base_name: str, run_id: str) -> str:
    return f"{base_name}_{run_id}"


def calculate_passhash(account_name: str, password: str) -> str:
    salt = hashlib.sha512(account_name.encode("utf-8")).hexdigest()
    src = f"{password}:{salt}"
    return hashlib.sha512(src.encode("utf-8")).hexdigest()


def _mime_to_ext(mime: str) -> str:
    if mime == "image/jpeg":
        return ".jpg"
    if mime == "image/png":
        return ".png"
    if mime == "image/gif":
        return ".gif"
    return ""


def _blob_service_client_from_env():
    global _blob_service_client
    if _blob_service_client is not None:
        return _blob_service_client

    conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    account_url = os.environ.get("AZURE_STORAGE_ACCOUNT_URL")

    if conn_str:
        _blob_service_client = BlobServiceClient.from_connection_string(conn_str)
    elif account_url:
        _blob_service_client = BlobServiceClient(
            account_url, credential=DefaultAzureCredential()
        )
    return _blob_service_client


def _blob_container_client():
    client = _blob_service_client_from_env()
    if client is None:
        return None
    return client.get_container_client(
        os.environ.get("AZURE_STORAGE_CONTAINER_NAME", "images")
    )


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


def run_seed(
    database_url: str,
    users_json: Path,
    posts_json: Path,
    images_zip: Path,
    extract_dir: Path,
    post_count: int,
    run_id: str | None = None,
    log=print,
) -> int:
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

    if not run_id:
        run_id = generate_run_id()
    log(f"[seed] run_id: {run_id}")

    container = _blob_container_client()
    conn = psycopg2.connect(database_url)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            user_ids: list[int] = []
            for entry in users_data:
                account_name = make_seed_account_name(entry.get("account_name"), run_id)
                password = entry.get("password")
                if not account_name or not password:
                    raise ValueError(
                        f"Each user entry must have account_name/password: {entry}"
                    )
                passhash = calculate_passhash(account_name, password)
                cur.execute(
                    """
                    INSERT INTO users (account_name, passhash, del_flg)
                    VALUES (%s, %s, 0)
                    ON CONFLICT (account_name)
                    DO UPDATE SET passhash = EXCLUDED.passhash, del_flg = 0
                    RETURNING id
                    """,
                    (account_name, passhash),
                )
                user_ids.append(cur.fetchone()[0])
            log(f"[seed] users ready: {len(user_ids)}")

            image_paths = extract_images(images_zip, extract_dir)
            if len(posts_data) < post_count:
                raise ValueError(
                    f"Not enough post texts: need {post_count}, got {len(posts_data)}"
                )
            if len(image_paths) < post_count:
                raise ValueError(
                    f"Not enough images: need {post_count}, got {len(image_paths)}"
                )

            created = 0
            for i in range(post_count):
                body = posts_data[i].get("body")
                if not body:
                    raise ValueError(f"Post entry at index {i} has no body")
                image_path = image_paths[i]
                mime = mimetypes.guess_type(str(image_path))[0]
                if mime not in ("image/jpeg", "image/png", "image/gif"):
                    raise ValueError(f"Unsupported image mime: {image_path} ({mime})")

                imgdata = image_path.read_bytes()
                user_id = user_ids[i % len(user_ids)]

                if container:
                    try:
                        blob_key = f"{uuid.uuid4()}{_mime_to_ext(mime)}"
                        container.upload_blob(
                            blob_key,
                            imgdata,
                            content_settings=ContentSettings(content_type=mime),
                            overwrite=True,
                        )
                        cur.execute(
                            """
                            INSERT INTO posts (user_id, mime, imgdata, body, img_blob_key)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (user_id, mime, psycopg2.Binary(b""), body, blob_key),
                        )
                    except Exception:
                        cur.execute(
                            """
                            INSERT INTO posts (user_id, mime, imgdata, body)
                            VALUES (%s, %s, %s, %s)
                            """,
                            (user_id, mime, psycopg2.Binary(imgdata), body),
                        )
                else:
                    cur.execute(
                        """
                        INSERT INTO posts (user_id, mime, imgdata, body)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (user_id, mime, psycopg2.Binary(imgdata), body),
                    )
                created += 1

        conn.commit()
        return created
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
