#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import random
import shlex
import subprocess
import uuid
import zipfile
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from dotenv import load_dotenv


DEFAULT_DB_URL = "postgresql://isuconp:isuconp@127.0.0.1:5432/isuconp?sslmode=disable"
ROOT_DIR = Path(__file__).resolve().parents[1]
AZURE_STORAGE_CONTAINER_NAME = os.environ.get("AZURE_STORAGE_CONTAINER_NAME", "images")

# Seed account name configuration
# Uses "_" separator (hyphen is rejected by validate_user regex [0-9a-zA-Z_]{3,})
SEED_RUN_ID_LENGTH = 8

# Comment seeding configuration.
# Three patterns are mixed so the dataset surfaces realistic load:
#   - heavy : heavy commenters (HEAVY_USER_RATIO of users) post on any post
#   - flame : any user piles onto flame posts (FLAME_POST_RATIO of posts)
#   - even  : random user × random post
HEAVY_USER_RATIO = 0.10
FLAME_POST_RATIO = 0.01
COMMENT_MIX = {"heavy": 0.5, "flame": 0.3, "even": 0.2}

HEAVY_COMMENT_TEMPLATES = [
    "いいね！",
    "わかる〜",
    "それな",
    "👍👍👍",
    "今日もチェックしてます！",
    "毎日楽しみにしてます",
    "応援してます！",
    "リアクションしました",
    "良い投稿ですね",
    "勉強になります",
    "シェアします！",
    "保存しました",
]

FLAME_COMMENT_TEMPLATES = [
    "それは違うと思います",
    "本当にそうですか？",
    "ソースありますか？",
    "意見が分かれそうですね",
    "炎上案件では…？",
    "賛否両論ありそう",
    "ちょっと配慮足りないのでは",
    "誤解を招く表現だと思います",
    "情報の正確性を確認したほうがよさそう",
    "コメント欄が荒れそうですね",
    "立場によって見方が変わりそう",
    "もう少し説明が欲しいです",
]

EVEN_COMMENT_TEMPLATES = [
    "参考になりました",
    "ありがとうございます",
    "投稿シェア感謝です",
    "知らなかったです",
    "なるほど！",
    "面白い視点ですね",
    "続報楽しみにしてます",
    "今度試してみます",
    "勉強になります",
    "良いまとめですね",
]


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


def seed_comments(
    cur,
    comment_count: int,
    rng: random.Random,
    run_id: str,
    heavy_user_rate: float | None = None,
    flame_post_rate: float | None = None,
    log=print,
) -> int:
    cur.execute("SELECT id FROM users WHERE del_flg = 0")
    user_ids = [row[0] for row in cur.fetchall()]
    cur.execute("SELECT id FROM posts")
    post_ids = [row[0] for row in cur.fetchall()]

    if not user_ids or not post_ids:
        log("[seed]   skipping comments: no users or posts in DB")
        return 0

    effective_heavy_rate = HEAVY_USER_RATIO if heavy_user_rate is None else heavy_user_rate
    effective_flame_rate = FLAME_POST_RATIO if flame_post_rate is None else flame_post_rate
    heavy_k = max(1, min(int(len(user_ids) * effective_heavy_rate), len(user_ids)))
    flame_k = max(1, min(int(len(post_ids) * effective_flame_rate), len(post_ids)))

    heavy_users = rng.sample(user_ids, heavy_k)
    flame_posts = rng.sample(post_ids, flame_k)
    log(
        f"[seed]   pool: users={len(user_ids)} posts={len(post_ids)}; "
        f"heavy_users={heavy_k} (rate={effective_heavy_rate}) "
        f"flame_posts={flame_k} (rate={effective_flame_rate})"
    )

    n_heavy = int(comment_count * COMMENT_MIX["heavy"])
    n_flame = int(comment_count * COMMENT_MIX["flame"])
    n_even = comment_count - n_heavy - n_flame
    log(f"[seed]   mix: heavy={n_heavy} flame={n_flame} even={n_even}")

    batch_size = 1000
    batch: list[tuple] = []
    created = 0
    insert_sql = "INSERT INTO comments (post_id, user_id, comment) VALUES %s"

    def flush(rows: list[tuple]) -> None:
        if not rows:
            return
        execute_values(cur, insert_sql, rows, page_size=batch_size)

    def append(post_id: int, user_id: int, template: str) -> None:
        nonlocal created
        # Suffix keeps each comment row distinct for debugging/traceability.
        body = f"{template} [#c{run_id}_{created + len(batch):08d}]"
        batch.append((post_id, user_id, body))
        if len(batch) >= batch_size:
            flush(batch)
            created += len(batch)
            batch.clear()
            if created % 10000 == 0:
                log(f"[seed]   inserted {created}/{comment_count}")

    for _ in range(n_heavy):
        append(rng.choice(post_ids), rng.choice(heavy_users), rng.choice(HEAVY_COMMENT_TEMPLATES))
    for _ in range(n_flame):
        append(rng.choice(flame_posts), rng.choice(user_ids), rng.choice(FLAME_COMMENT_TEMPLATES))
    for _ in range(n_even):
        append(rng.choice(post_ids), rng.choice(user_ids), rng.choice(EVEN_COMMENT_TEMPLATES))

    if batch:
        flush(batch)
        created += len(batch)
        batch.clear()

    log(f"[seed]   created {created} comments")
    return created


def run_seed(
    users_json: Path,
    posts_json: Path,
    images_zip: Path,
    extract_dir: Path,
    post_count: int,
    user_count: int | None = None,
    comment_count: int | None = None,
    heavy_user_rate: float | None = None,
    flame_post_rate: float | None = None,
    run_id: str | None = None,
    log=print,
) -> int:
    if post_count <= 0:
        raise ValueError("--post-count must be greater than 0")
    if user_count is not None and user_count <= 0:
        raise ValueError("--user-count must be greater than 0")
    if comment_count is not None and comment_count < 0:
        raise ValueError("--comment-count must be >= 0")
    if heavy_user_rate is not None and not (0 < heavy_user_rate <= 1):
        raise ValueError("--heavy-user-rate must be in (0, 1]")
    if flame_post_rate is not None and not (0 < flame_post_rate <= 1):
        raise ValueError("--flame-post-rate must be in (0, 1]")

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

    log("[seed] Step 1/4: create/update users")

    database_url = resolve_database_url() or DEFAULT_DB_URL
    container = blob_container_client()

    conn = psycopg2.connect(database_url)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            effective_user_count = user_count if user_count is not None else len(users_data)
            user_ids: list[int] = []
            for i in range(effective_user_count):
                entry = users_data[i % len(users_data)]
                cycle = i // len(users_data)
                base_account_id = entry.get("account_id") or entry.get("account_name")
                # cycle 0 keeps the original "<base>_<run_id>" format for backward
                # compatibility; further cycles append "_<cycle>" so account_ids stay unique.
                account_id = make_seed_account_id(base_account_id, run_id)
                if cycle > 0:
                    account_id = f"{account_id}_{cycle}"
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
                if effective_user_count > len(users_data) and (i + 1) % 1000 == 0:
                    log(f"[seed]   users created: {i + 1}/{effective_user_count}")

            log(f"[seed]   users ready: {len(user_ids)}")

            log("[seed] Step 2/4: extract images.zip")
            image_paths = extract_images(images_zip, extract_dir)
            log(f"[seed]   extracted images found: {len(image_paths)}")

            log("[seed] Step 3/4: create demo posts with images")
            if not posts_data:
                raise ValueError(f"No post texts in {posts_json}")
            if not image_paths:
                raise ValueError("No images extracted")
            for idx, entry in enumerate(posts_data):
                if not entry.get("body"):
                    raise ValueError(f"Post entry at index {idx} has no body")

            # Preload image bytes + mime, and upload each image once to blob storage.
            # Posts then reference the cached blob_key — avoids re-uploading the same
            # 100 images millions of times.
            image_mimes: list[str] = []
            image_bytes: list[bytes] = []
            image_blob_keys: list[str | None] = []
            for image_path in image_paths:
                mime = mimetypes.guess_type(str(image_path))[0]
                if mime not in ("image/jpeg", "image/png", "image/gif"):
                    raise ValueError(
                        f"Unsupported image mime for {image_path}: {mime}"
                    )
                imgdata = image_path.read_bytes()
                image_mimes.append(mime)
                image_bytes.append(imgdata)

                blob_key: str | None = None
                if container:
                    try:
                        blob_key = f"{uuid.uuid4()}{_mime_to_ext(mime)}"
                        container.upload_blob(
                            blob_key,
                            imgdata,
                            content_settings=ContentSettings(content_type=mime),
                            overwrite=True,
                        )
                    except Exception:
                        log(
                            f"[seed]   warning: blob upload failed for {image_path.name}; fallback to DB imgdata"
                        )
                        blob_key = None
                image_blob_keys.append(blob_key)

            uploaded = sum(1 for k in image_blob_keys if k)
            log(
                f"[seed]   uploaded {uploaded}/{len(image_paths)} images to blob storage"
            )

            rng = random.Random(run_id)
            batch_size = 500
            batch: list[tuple] = []
            created = 0
            insert_sql = (
                "INSERT INTO posts (user_id, mime, imgdata, body, img_blob_key) VALUES %s"
            )

            def flush(rows: list[tuple]) -> None:
                if not rows:
                    return
                execute_values(cur, insert_sql, rows, page_size=batch_size)

            for i in range(post_count):
                base_body = posts_data[i % len(posts_data)]["body"]
                # Append a unique suffix so each post body is distinct even when
                # cycling through the limited base bodies.
                body = f"{base_body} [#{run_id}_{i:07d}]"

                user_id = rng.choice(user_ids)
                img_idx = rng.randrange(len(image_paths))
                mime = image_mimes[img_idx]
                blob_key = image_blob_keys[img_idx]

                if blob_key:
                    batch.append(
                        (user_id, mime, psycopg2.Binary(b""), body, blob_key)
                    )
                else:
                    batch.append(
                        (
                            user_id,
                            mime,
                            psycopg2.Binary(image_bytes[img_idx]),
                            body,
                            None,
                        )
                    )

                if len(batch) >= batch_size:
                    flush(batch)
                    created += len(batch)
                    batch.clear()
                    if created % 10000 == 0:
                        log(f"[seed]   inserted {created}/{post_count}")

            if batch:
                flush(batch)
                created += len(batch)
                batch.clear()

            effective_comment_count = (
                comment_count if comment_count is not None else post_count * 3
            )
            comments_created = 0
            if effective_comment_count > 0:
                log(
                    f"[seed] Step 4/4: create {effective_comment_count} comments "
                    f"(heavy/flame/even mix over DB-wide users and posts)"
                )
                comments_created = seed_comments(
                    cur=cur,
                    comment_count=effective_comment_count,
                    rng=rng,
                    run_id=run_id,
                    heavy_user_rate=heavy_user_rate,
                    flame_post_rate=flame_post_rate,
                    log=log,
                )
            else:
                log("[seed] Step 4/4: skipped (comment-count=0)")

        conn.commit()
        log(
            f"[seed] done: created {created} posts, {comments_created} comments"
        )
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
        "--user-count",
        type=int,
        default=None,
        help="Number of users to create (default: len(users JSON)). Cycles through base users with a _<cycle> suffix.",
    )
    parser.add_argument(
        "--comment-count",
        type=int,
        default=None,
        help="Number of comments to create (default: post_count * 3). 0 disables comment seeding.",
    )
    parser.add_argument(
        "--heavy-user-rate",
        type=float,
        default=None,
        help=(
            "Fraction of DB users that act as heavy commenters, in (0, 1]. "
            f"Default: {HEAVY_USER_RATIO}."
        ),
    )
    parser.add_argument(
        "--flame-post-rate",
        type=float,
        default=None,
        help=(
            "Fraction of DB posts that act as flame posts, in (0, 1]. "
            f"Default: {FLAME_POST_RATIO}."
        ),
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
        user_count=args.user_count,
        comment_count=args.comment_count,
        heavy_user_rate=args.heavy_user_rate,
        flame_post_rate=args.flame_post_rate,
        run_id=args.run_id,
        log=print,
    )


if __name__ == "__main__":
    raise SystemExit(main())
