#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shlex
import subprocess
import uuid
import zipfile
from pathlib import Path

import psycopg2
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from dotenv import load_dotenv


DEFAULT_DB_URL = "postgresql://isuconp:isuconp@127.0.0.1:5432/isuconp?sslmode=disable"
ROOT_DIR = Path(__file__).resolve().parents[1]
AZURE_STORAGE_CONTAINER_NAME = os.environ.get("AZURE_STORAGE_CONTAINER_NAME", "images")

# Seed account name configuration
# Uses "_" separator (hyphen is rejected by validate_user regex [0-9a-zA-Z_]{3,})
SEED_RUN_ID_LENGTH = 8


def generate_run_id() -> str:
    return uuid.uuid4().hex[:SEED_RUN_ID_LENGTH]


def make_seed_account_id(base_id: str, run_id: str) -> str:
    return f"{base_id}_{run_id}"

_blob_service_client = None


def load_env() -> None:
    env_file = ROOT_DIR / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)


def digest(src: str) -> str:
    out = subprocess.check_output(
        f"printf %s {shlex.quote(src)} | openssl dgst -sha512 | sed 's/^.*= //'",
        shell=True,
        encoding="utf-8",
    )
    return out.strip()


def calculate_salt(account_id: str) -> str:
    return digest(account_id)


def calculate_passhash(account_id: str, password: str) -> str:
    return digest(f"{password}:{calculate_salt(account_id)}")


def resolve_database_url() -> str:
    database_url = os.environ.get("ISUCONP_DATABASE_URL")
    if database_url:
        return database_url

    host = os.environ.get("ISUCONP_DB_HOST", "127.0.0.1")
    port = os.environ.get("ISUCONP_DB_PORT", "5432")
    user = os.environ.get("ISUCONP_DB_USER", "isuconp")
    password = os.environ.get("ISUCONP_DB_PASSWORD", "isuconp")
    dbname = os.environ.get("ISUCONP_DB_NAME", "isuconp")
    sslmode = os.environ.get("ISUCONP_DB_SSLMODE", "disable")
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}?sslmode={sslmode}"


def _mime_to_ext(mime: str) -> str:
    if mime == "image/jpeg":
        return ".jpg"
    if mime == "image/png":
        return ".png"
    if mime == "image/gif":
        return ".gif"
    return ""


def blob_service_client():
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


def blob_container_client():
    client = blob_service_client()
    if client is None:
        return None
    return client.get_container_client(AZURE_STORAGE_CONTAINER_NAME)


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def extract_images(images_zip: Path, extract_dir: Path) -> list[Path]:
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(images_zip) as zf:
        zf.extractall(extract_dir)

    image_paths = sorted(
        p
        for p in extract_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif"}
    )
    return image_paths


def run_seed(
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

    log("[seed] Step 1/3: create/update users")

    database_url = resolve_database_url() or DEFAULT_DB_URL
    container = blob_container_client()

    conn = psycopg2.connect(database_url)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            user_ids: list[int] = []
            for entry in users_data:
                base_account_id = entry.get("account_id") or entry.get("account_name")
                account_id = make_seed_account_id(base_account_id, run_id)
                password = entry.get("password")
                if not account_id or not password:
                    raise ValueError(
                        f"Each user entry must have account_id/password: {entry}"
                    )
                passhash = calculate_passhash(account_id, password)
                cur.execute(
                    """
                    INSERT INTO users (account_id, passhash, del_flg)
                    VALUES (%s, %s, 0)
                    ON CONFLICT (account_id)
                    DO UPDATE SET passhash = EXCLUDED.passhash, del_flg = 0
                    RETURNING id
                    """,
                    (account_id, passhash),
                )
                user_ids.append(cur.fetchone()[0])

            log(f"[seed]   users ready: {len(user_ids)}")

            log("[seed] Step 2/3: extract images.zip")
            image_paths = extract_images(images_zip, extract_dir)
            log(f"[seed]   extracted images found: {len(image_paths)}")

            log("[seed] Step 3/3: create demo posts with images")
            if len(posts_data) < post_count:
                raise ValueError(
                    f"Not enough post texts in {posts_json}: need {post_count}, got {len(posts_data)}"
                )
            if len(image_paths) < post_count:
                raise ValueError(
                    f"Not enough images after extraction: need {post_count}, got {len(image_paths)}"
                )

            created = 0
            for i in range(post_count):
                body = posts_data[i].get("body")
                if not body:
                    raise ValueError(f"Post entry at index {i} has no body")

                image_path = image_paths[i]
                mime = mimetypes.guess_type(str(image_path))[0]
                if mime not in ("image/jpeg", "image/png", "image/gif"):
                    raise ValueError(
                        f"Unsupported image mime for {image_path}: {mime}"
                    )

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
                        log(
                            f"[seed]   warning: blob upload failed for {image_path.name}; fallback to DB imgdata"
                        )
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
        log(f"[seed] done: created {created} posts")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return 0


def main() -> int:
    load_env()
    global AZURE_STORAGE_CONTAINER_NAME
    AZURE_STORAGE_CONTAINER_NAME = os.environ.get(
        "AZURE_STORAGE_CONTAINER_NAME", "images"
    )

    parser = argparse.ArgumentParser(description="Seed demo users and posts")
    parser.add_argument(
        "--users-json",
        default="data/demo_users.json",
        help="Path to demo users JSON",
    )
    parser.add_argument(
        "--posts-json",
        default="data/demo_posts_text.json",
        help="Path to demo post bodies JSON",
    )
    parser.add_argument(
        "--images-zip",
        default="data/images.zip",
        help="Path to image zip file",
    )
    parser.add_argument(
        "--extract-dir",
        default="data",
        help="Extraction directory for images zip",
    )
    parser.add_argument(
        "--post-count",
        type=int,
        default=100,
        help="Number of posts to create",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Run ID suffix for account names (auto-generated if omitted)",
    )
    args = parser.parse_args()

    return run_seed(
        users_json=Path(args.users_json),
        posts_json=Path(args.posts_json),
        images_zip=Path(args.images_zip),
        extract_dir=Path(args.extract_dir),
        post_count=args.post_count,
        run_id=args.run_id,
        log=print,
    )


if __name__ == "__main__":
    raise SystemExit(main())
