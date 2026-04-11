import json
import logging
import os
import tempfile
from pathlib import Path

import azure.functions as func

from api_seed_runner import run_seed_via_api

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
logger = logging.getLogger(__name__)


def _default_path(value: str | None, fallback: str) -> Path:
    if value:
        return Path(value)
    return Path(__file__).resolve().parent / fallback


def _default_extract_dir(value: str | None) -> Path:
    if value:
        return Path(value)
    return Path(tempfile.gettempdir()) / "isuconp-seed-extracted"


@app.route(route="seed-now", methods=["POST"])
def seed_now(req: func.HttpRequest) -> func.HttpResponse:
    api_base_url = os.environ.get("API_BASE_URL")
    if not api_base_url:
        return func.HttpResponse(
            json.dumps({"ok": False, "error": "API_BASE_URL is required"}),
            status_code=500,
            mimetype="application/json",
        )

    try:
        body = req.get_json()
    except ValueError:
        body = {}

    users_json = _default_path(
        body.get("users_json") if isinstance(body, dict) else None,
        "data/demo_users.json",
    )
    posts_json = _default_path(
        body.get("posts_json") if isinstance(body, dict) else None,
        "data/demo_posts_text.json",
    )
    images_zip = _default_path(
        body.get("images_zip") if isinstance(body, dict) else None,
        "data/images.zip",
    )
    extract_dir = _default_extract_dir(
        body.get("extract_dir") if isinstance(body, dict) else None
    )
    post_count = int(
        (
            body.get("post_count")
            if isinstance(body, dict) and body.get("post_count") is not None
            else os.environ.get("SEED_POST_COUNT", "100")
        )
    )
    run_id = (
        body.get("run_id")
        if isinstance(body, dict)
        else None
    )

    try:
        created = run_seed_via_api(
            api_base_url=body.get("api_base_url") if isinstance(body, dict) and body.get("api_base_url") else api_base_url,
            users_json=users_json,
            posts_json=posts_json,
            images_zip=images_zip,
            extract_dir=extract_dir,
            post_count=post_count,
            run_id=run_id,
            log=logger.info,
        )
        return func.HttpResponse(
            json.dumps({"ok": True, "created_posts": created}, ensure_ascii=False),
            status_code=200,
            mimetype="application/json",
        )
    except Exception as exc:
        logger.exception("seed execution failed")
        return func.HttpResponse(
            json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False),
            status_code=500,
            mimetype="application/json",
        )
