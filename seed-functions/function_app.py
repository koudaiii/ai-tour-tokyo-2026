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


def _execute_seed(params: dict) -> dict:
    """Common seed execution logic shared across all triggers."""
    api_base_url = params.get("api_base_url") or os.environ.get("API_BASE_URL")
    if not api_base_url:
        raise ValueError("API_BASE_URL is required")

    users_json = _default_path(params.get("users_json"), "data/demo_users.json")
    posts_json = _default_path(params.get("posts_json"), "data/demo_posts_text.json")
    images_zip = _default_path(params.get("images_zip"), "data/images.zip")
    extract_dir = _default_extract_dir(params.get("extract_dir"))
    post_count = int(
        params.get("post_count") or os.environ.get("SEED_POST_COUNT", "100")
    )
    run_id = params.get("run_id")

    created = run_seed_via_api(
        api_base_url=api_base_url,
        users_json=users_json,
        posts_json=posts_json,
        images_zip=images_zip,
        extract_dir=extract_dir,
        post_count=post_count,
        run_id=run_id,
        log=logger.info,
    )
    return {"ok": True, "created_posts": created}


# ---------------------------------------------------------------------------
# HTTP trigger (existing)
# ---------------------------------------------------------------------------
@app.route(route="seed-now", methods=["POST"])
def seed_now(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        body = {}

    params = body if isinstance(body, dict) else {}

    try:
        result = _execute_seed(params)
        return func.HttpResponse(
            json.dumps(result, ensure_ascii=False),
            status_code=200,
            mimetype="application/json",
        )
    except Exception as exc:
        logger.exception("seed_now failed")
        return func.HttpResponse(
            json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False),
            status_code=500,
            mimetype="application/json",
        )


# ---------------------------------------------------------------------------
# Timer trigger
#   Schedule is read from app setting SEED_TIMER_SCHEDULE (NCRONTAB format).
#   Example: "0 0 0 * * *" = daily at midnight UTC
#   Disable via app setting: AzureWebJobs.seed_timer.Disabled = true
# ---------------------------------------------------------------------------
@app.timer_trigger(
    schedule="%SEED_TIMER_SCHEDULE%",
    arg_name="timer",
    run_on_startup=False,
)
def seed_timer(timer: func.TimerRequest) -> None:
    logger.info("seed_timer triggered (past_due=%s)", timer.past_due)
    try:
        result = _execute_seed({})
        logger.info("seed_timer completed: %s", result)
    except Exception:
        logger.exception("seed_timer failed")
        raise


# ---------------------------------------------------------------------------
# Queue Storage trigger
#   Enqueue a JSON message to the "seed-jobs" queue to start a seed run.
#   Message body: {"post_count": 50, "run_id": "abc12345"} (all fields optional)
#   Uses the same storage account as the Functions runtime (AzureWebJobsStorage).
# ---------------------------------------------------------------------------
@app.queue_trigger(
    arg_name="msg",
    queue_name="seed-jobs",
    connection="AzureWebJobsStorage",
)
def seed_queue(msg: func.QueueMessage) -> None:
    logger.info("seed_queue triggered (id=%s)", msg.id)
    try:
        params = json.loads(msg.get_body().decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        params = {}

    if not isinstance(params, dict):
        params = {}

    try:
        result = _execute_seed(params)
        logger.info("seed_queue completed: %s", result)
    except Exception:
        logger.exception("seed_queue failed")
        raise


# ---------------------------------------------------------------------------
# Event Grid trigger
#   Subscribe an Event Grid topic to this endpoint.
#   Seed parameters are read from the event data payload.
# ---------------------------------------------------------------------------
@app.event_grid_trigger(arg_name="event")
def seed_event_grid(event: func.EventGridEvent) -> None:
    logger.info(
        "seed_event_grid triggered (id=%s, type=%s, subject=%s)",
        event.id,
        event.event_type,
        event.subject,
    )
    try:
        params = event.get_json()
    except Exception:
        params = {}

    if not isinstance(params, dict):
        params = {}

    try:
        result = _execute_seed(params)
        logger.info("seed_event_grid completed: %s", result)
    except Exception:
        logger.exception("seed_event_grid failed")
        raise
