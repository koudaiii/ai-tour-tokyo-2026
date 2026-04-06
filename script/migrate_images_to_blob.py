#!/usr/bin/env python3
"""Migrate existing images from PostgreSQL bytea to Azure Blob Storage.

Usage:
    AZURE_STORAGE_CONNECTION_STRING="..." python script/migrate_images_to_blob.py

Or with Managed Identity:
    AZURE_STORAGE_ACCOUNT_URL="https://account.blob.core.windows.net" python script/migrate_images_to_blob.py

Environment variables:
    AZURE_STORAGE_CONNECTION_STRING  Connection string (dev)
    AZURE_STORAGE_ACCOUNT_URL        Account URL for DefaultAzureCredential (prod)
    AZURE_STORAGE_CONTAINER_NAME     Container name (default: images)
    ISUCONP_DATABASE_URL             PostgreSQL URL (default: postgresql://isuconp:isuconp@127.0.0.1:5432/isuconp)
"""

import os
import sys
import uuid

import psycopg2
import psycopg2.extras
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from dotenv import load_dotenv


def _mime_to_ext(mime):
    if mime == "image/jpeg":
        return ".jpg"
    elif mime == "image/png":
        return ".png"
    elif mime == "image/gif":
        return ".gif"
    return ""


def main():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(root_dir, ".env"))

    # Setup Blob Storage client
    conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    account_url = os.environ.get("AZURE_STORAGE_ACCOUNT_URL")
    container_name = os.environ.get("AZURE_STORAGE_CONTAINER_NAME", "images")

    if conn_str:
        blob_service = BlobServiceClient.from_connection_string(conn_str)
    elif account_url:
        blob_service = BlobServiceClient(account_url, credential=DefaultAzureCredential())
    else:
        print("Error: Set AZURE_STORAGE_CONNECTION_STRING or AZURE_STORAGE_ACCOUNT_URL")
        sys.exit(1)

    container = blob_service.get_container_client(container_name)

    # Setup DB connection
    database_url = os.environ.get(
        "ISUCONP_DATABASE_URL",
        "postgresql://isuconp:isuconp@127.0.0.1:5432/isuconp",
    )
    conn = psycopg2.connect(
        database_url,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
    conn.autocommit = True

    # Find posts that have imgdata but no img_blob_key
    cur = conn.cursor()
    cur.execute(
        "SELECT id, mime, imgdata FROM posts WHERE img_blob_key IS NULL AND length(imgdata) > 0"
    )
    posts = cur.fetchall()

    total = len(posts)
    print(f"Found {total} images to migrate")

    migrated = 0
    skipped = 0
    for post in posts:
        blob_key = f"{uuid.uuid4()}{_mime_to_ext(post['mime'])}"

        try:
            container.upload_blob(
                blob_key,
                bytes(post["imgdata"]),
                content_settings=ContentSettings(content_type=post["mime"]),
                overwrite=False,
            )
        except Exception as e:
            print(f"  [SKIP] Post {post['id']}: {e}")
            skipped += 1
            continue

        cur.execute(
            "UPDATE posts SET img_blob_key = %s WHERE id = %s",
            (blob_key, post["id"]),
        )
        migrated += 1

        if migrated % 100 == 0:
            print(f"  Progress: {migrated}/{total}")

    print(f"Done: {migrated} migrated, {skipped} skipped, {total} total")


if __name__ == "__main__":
    main()
