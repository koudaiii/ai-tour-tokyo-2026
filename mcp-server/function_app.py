"""Azure Functions Remote MCP Server for Private ISU.

Scenario-based tools that combine multiple API calls to provide
high-level functionality that APIM's 1:1 proxy cannot offer.
"""

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

import azure.functions as func
import psycopg2
import psycopg2.extras

app = func.FunctionApp()

logger = logging.getLogger(__name__)

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8080")
API_TIMEOUT_SECONDS = float(os.environ.get("API_TIMEOUT_SECONDS", "10"))


class ApiError(Exception):
    """Raised when the upstream API call fails, times out, or is unreachable."""


def _api_get(path: str, params: dict | None = None) -> dict:
    url = f"{API_BASE_URL}{path}"
    if params:
        filtered = {k: v for k, v in params.items() if v is not None}
        if filtered:
            url += "?" + urllib.parse.urlencode(filtered)
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=API_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ApiError(f"Not found: {path}") from e
        raise ApiError(f"API error: {e.code} {e.reason}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        reason = getattr(e, "reason", e)
        raise ApiError(f"API unreachable (timeout={API_TIMEOUT_SECONDS}s): {reason}") from e


def _parse_args(context) -> dict:
    """Parse tool arguments from the MCP trigger context."""
    content = json.loads(context)
    return content.get("arguments", content)


# ---------------------------------------------------------------------------
# Scenario 1: browse_timeline
# ---------------------------------------------------------------------------
@app.mcp_tool_trigger(
    arg_name="context",
    tool_name="browse_timeline",
    description=(
        "Browse the social media timeline. Returns a digest of recent posts "
        "with engagement metrics (comment counts). Supports keyword filtering "
        "and cursor-based pagination. Use this as the starting point to "
        "understand what is happening on the platform. "
        "NOTE: returned `author` / `latest_commenters` are string handles "
        "(`users.account_id`), not numeric user IDs."
    ),
    tool_properties=json.dumps([
        {
            "propertyName": "keyword",
            "propertyType": "string",
            "description": "Optional keyword to filter posts (searches post body text)",
            "isRequired": False,
        },
        {
            "propertyName": "max_created_at",
            "propertyType": "string",
            "description": "ISO8601 cursor for pagination — fetch posts older than this timestamp",
            "isRequired": False,
        },
        {
            "propertyName": "limit",
            "propertyType": "number",
            "description": "Max number of posts to return (default 10, max 20)",
            "isRequired": False,
        },
    ]),
)
def browse_timeline(context: str) -> str:
    args = _parse_args(context)
    keyword = (args.get("keyword") or "").lower()
    limit = min(int(args.get("limit") or 10), 20)

    params = {}
    if args.get("max_created_at"):
        params["max_created_at"] = args["max_created_at"]

    try:
        data = _api_get("/api/posts", params)
    except ApiError as e:
        return json.dumps({"error": str(e)})

    posts = data.get("posts", [])

    if keyword:
        posts = [p for p in posts if keyword in (p.get("body") or "").lower()]

    posts = posts[:limit]

    digest = []
    for p in posts:
        digest.append({
            "id": p["id"],
            "author": p["user"]["account_id"],
            "body_preview": (p["body"] or "")[:120],
            "image_url": p.get("image_url"),
            "comment_count": p["comment_count"],
            "latest_commenters": list({
                c["user"]["account_id"] for c in (p.get("comments") or [])
            }),
            "created_at": p["created_at"],
        })

    next_cursor = posts[-1]["created_at"] if posts else None

    return json.dumps({
        "total_fetched": len(digest),
        "next_cursor": next_cursor,
        "posts": digest,
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Scenario 2: explore_user
# ---------------------------------------------------------------------------
@app.mcp_tool_trigger(
    arg_name="context",
    tool_name="explore_user",
    description=(
        "Get a comprehensive view of a user: profile, activity statistics, "
        "and their recent posts with comments — all in a single call. "
        "Use this to understand who a user is and what they have been posting. "
        "NOTE: `account_id` is the user's string handle (e.g. \"terra\"), "
        "NOT the numeric `users.id` column."
    ),
    tool_properties=json.dumps([
        {
            "propertyName": "account_id",
            "propertyType": "string",
            "description": (
                "String username / handle of the user (e.g. \"terra\", \"mary\"). "
                "This is the `users.account_id` column, NOT the numeric `users.id`. "
                "Do not pass numbers like 1 or 42 here."
            ),
            "isRequired": True,
        },
    ]),
)
def explore_user(context: str) -> str:
    args = _parse_args(context)
    account_id = args.get("account_id")
    if not account_id:
        return json.dumps({"error": "account_id is required"})

    safe_name = urllib.parse.quote(account_id)

    try:
        profile = _api_get(f"/api/users/{safe_name}")
    except ApiError as e:
        return json.dumps({"error": f"User not found or API error: {e}"})

    try:
        posts_data = _api_get(f"/api/users/{safe_name}/posts")
    except ApiError:
        posts_data = {"posts": []}

    posts = posts_data.get("posts", [])

    total_comments_received = sum(p.get("comment_count", 0) for p in posts)
    avg_comments = (
        round(total_comments_received / len(posts), 1) if posts else 0
    )

    recent_posts = []
    for p in posts[:5]:
        recent_posts.append({
            "id": p["id"],
            "body_preview": (p["body"] or "")[:120],
            "image_url": p.get("image_url"),
            "comment_count": p["comment_count"],
            "created_at": p["created_at"],
        })

    return json.dumps({
        "user": profile.get("user"),
        "stats": {
            "post_count": profile.get("post_count", 0),
            "comment_count": profile.get("comment_count", 0),
            "commented_count": profile.get("commented_count", 0),
            "avg_comments_per_post": avg_comments,
        },
        "recent_posts": recent_posts,
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Scenario 3: find_popular_posts
# ---------------------------------------------------------------------------
@app.mcp_tool_trigger(
    arg_name="context",
    tool_name="find_popular_posts",
    description=(
        "Find the most popular (most commented) posts on the platform. "
        "The API only returns posts in chronological order, but this tool "
        "re-ranks them by engagement. Use this to discover trending content. "
        "NOTE: returned `author` / `commenters` are string handles "
        "(`users.account_id`), not numeric user IDs."
    ),
    tool_properties=json.dumps([
        {
            "propertyName": "min_comments",
            "propertyType": "number",
            "description": "Only return posts with at least this many comments (default 1)",
            "isRequired": False,
        },
        {
            "propertyName": "limit",
            "propertyType": "number",
            "description": "Max number of posts to return (default 5, max 20)",
            "isRequired": False,
        },
    ]),
)
def find_popular_posts(context: str) -> str:
    args = _parse_args(context)
    min_comments = int(args.get("min_comments") or 1)
    limit = min(int(args.get("limit") or 5), 20)

    try:
        data = _api_get("/api/posts")
    except ApiError as e:
        return json.dumps({"error": str(e)})

    posts = data.get("posts", [])
    posts = [p for p in posts if p.get("comment_count", 0) >= min_comments]
    posts.sort(key=lambda p: p.get("comment_count", 0), reverse=True)
    posts = posts[:limit]

    results = []
    for p in posts:
        results.append({
            "id": p["id"],
            "author": p["user"]["account_id"],
            "body_preview": (p["body"] or "")[:120],
            "image_url": p.get("image_url"),
            "comment_count": p["comment_count"],
            "commenters": list({
                c["user"]["account_id"] for c in (p.get("comments") or [])
            }),
            "created_at": p["created_at"],
        })

    return json.dumps({
        "total": len(results),
        "posts": results,
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Scenario 4: get_conversation
# ---------------------------------------------------------------------------
@app.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_conversation",
    description=(
        "Get a post and its full comment thread formatted as a readable "
        "conversation. Returns the original post followed by all comments "
        "in chronological order, making it easy to follow the discussion. "
        "NOTE: returned `author` is a string handle (`users.account_id`), "
        "not a numeric user ID."
    ),
    tool_properties=json.dumps([
        {
            "propertyName": "post_id",
            "propertyType": "number",
            "description": "The ID of the post to view the conversation for",
            "isRequired": True,
        },
    ]),
)
def get_conversation(context: str) -> str:
    args = _parse_args(context)
    post_id = args.get("post_id")
    if not post_id:
        return json.dumps({"error": "post_id is required"})

    try:
        data = _api_get(f"/api/posts/{int(post_id)}")
    except ApiError as e:
        return json.dumps({"error": str(e)})

    post = data.get("post")
    if not post:
        return json.dumps({"error": "post not found"})

    thread = []
    thread.append({
        "type": "post",
        "author": post["user"]["account_id"],
        "body": post["body"],
        "image_url": post.get("image_url"),
        "created_at": post["created_at"],
    })

    for c in post.get("comments", []):
        thread.append({
            "type": "comment",
            "author": c["user"]["account_id"],
            "body": c["comment"],
            "created_at": c["created_at"],
        })

    return json.dumps({
        "post_id": post["id"],
        "total_comments": post.get("comment_count", 0),
        "thread": thread,
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Scenario 5: compare_users
# ---------------------------------------------------------------------------
@app.mcp_tool_trigger(
    arg_name="context",
    tool_name="compare_users",
    description=(
        "Compare activity statistics of two or more users side by side. "
        "Shows post counts, comment counts, and engagement metrics for each "
        "user. Useful for understanding relative activity levels. "
        "NOTE: `account_ids` are string handles (e.g. \"terra,mary\"), "
        "NOT the numeric `users.id` column."
    ),
    tool_properties=json.dumps([
        {
            "propertyName": "account_ids",
            "propertyType": "string",
            "description": (
                "Comma-separated list of string usernames / handles to compare "
                "(2-5 users, e.g. \"terra,mary,john\"). These are values of the "
                "`users.account_id` column, NOT the numeric `users.id`. "
                "Do not pass numbers like \"1,2,3\" here."
            ),
            "isRequired": True,
        },
    ]),
)
def compare_users(context: str) -> str:
    args = _parse_args(context)
    raw = args.get("account_ids", "")
    names = [n.strip() for n in raw.split(",") if n.strip()]

    if len(names) < 2:
        return json.dumps({"error": "Provide at least 2 account IDs separated by commas"})
    if len(names) > 5:
        names = names[:5]

    comparisons = []
    for name in names:
        safe = urllib.parse.quote(name)
        try:
            profile = _api_get(f"/api/users/{safe}")
            comparisons.append({
                "account_id": name,
                "post_count": profile.get("post_count", 0),
                "comment_count": profile.get("comment_count", 0),
                "commented_count": profile.get("commented_count", 0),
                "created_at": profile.get("user", {}).get("created_at"),
            })
        except ApiError as e:
            comparisons.append({
                "account_id": name,
                "error": str(e),
            })

    return json.dumps({
        "users": comparisons,
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Scenario 6: search_posts
# ---------------------------------------------------------------------------
@app.mcp_tool_trigger(
    arg_name="context",
    tool_name="search_posts",
    description=(
        "Search posts by keyword. The underlying API has no search endpoint, "
        "so this tool fetches recent posts and filters them by matching "
        "the keyword against post body text and commenter names. "
        "Returns matching posts ranked by relevance. "
        "NOTE: `query` can also match author / commenter handles since those "
        "are string `account_id`s (not numeric user IDs); the returned "
        "`author` field is likewise a string handle."
    ),
    tool_properties=json.dumps([
        {
            "propertyName": "query",
            "propertyType": "string",
            "description": "Search keyword or phrase to look for in post body and comments",
            "isRequired": True,
        },
        {
            "propertyName": "limit",
            "propertyType": "number",
            "description": "Max results to return (default 5, max 20)",
            "isRequired": False,
        },
    ]),
)
def search_posts(context: str) -> str:
    args = _parse_args(context)
    query = (args.get("query") or "").lower()
    if not query:
        return json.dumps({"error": "query is required"})

    limit = min(int(args.get("limit") or 5), 20)

    try:
        data = _api_get("/api/posts")
    except ApiError as e:
        return json.dumps({"error": str(e)})

    posts = data.get("posts", [])

    scored = []
    for p in posts:
        score = 0
        body = (p.get("body") or "").lower()
        if query in body:
            score += 10
            score += body.count(query)

        for c in p.get("comments", []):
            comment_text = (c.get("comment") or "").lower()
            if query in comment_text:
                score += 3
            commenter = (c.get("user", {}).get("account_id") or "").lower()
            if query in commenter:
                score += 1

        author = (p.get("user", {}).get("account_id") or "").lower()
        if query in author:
            score += 5

        if score > 0:
            scored.append((score, p))

    scored.sort(key=lambda x: x[0], reverse=True)
    scored = scored[:limit]

    results = []
    for score, p in scored:
        results.append({
            "id": p["id"],
            "relevance_score": score,
            "author": p["user"]["account_id"],
            "body_preview": (p["body"] or "")[:200],
            "image_url": p.get("image_url"),
            "comment_count": p["comment_count"],
            "created_at": p["created_at"],
        })

    return json.dumps({
        "query": query,
        "total_matches": len(results),
        "results": results,
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Scenario 7: inspect_active_queries
# ---------------------------------------------------------------------------
@app.mcp_tool_trigger(
    arg_name="context",
    tool_name="inspect_active_queries",
    description=(
        "Inspect currently running PostgreSQL queries from pg_stat_activity, "
        "ordered by how long each query has been running. Connects via "
        "ISUCONP_DATABASE_URL. Use this to diagnose slow queries, lock "
        "contention, or N+1 issues during load tests."
    ),
    tool_properties=json.dumps([
        {
            "propertyName": "limit",
            "propertyType": "number",
            "description": "Max number of active sessions to return (default 10, max 50)",
            "isRequired": False,
        },
        {
            "propertyName": "min_duration_ms",
            "propertyType": "number",
            "description": "Only return queries running longer than this in milliseconds (default 0)",
            "isRequired": False,
        },
    ]),
)
def inspect_active_queries(context: str) -> str:
    args = _parse_args(context)
    limit = min(int(args.get("limit") or 10), 50)
    min_duration_ms = int(args.get("min_duration_ms") or 0)

    dsn = os.environ.get("ISUCONP_DATABASE_URL")
    if not dsn:
        return json.dumps({"error": "ISUCONP_DATABASE_URL is not set"})

    activity_sql = """
        SELECT
            pid,
            usename,
            datname,
            now() - query_start AS duration,
            state,
            query
        FROM pg_stat_activity
        WHERE state = 'active'
        ORDER BY duration DESC
    """

    try:
        with psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor) as conn:
            with conn.cursor() as cur:
                cur.execute("SET statement_timeout = 2000")
                cur.execute(activity_sql)
                rows = cur.fetchall()
    except psycopg2.Error as e:
        return json.dumps({"error": f"DB error: {str(e).strip()}"})

    sessions: list[dict] = []
    for row in rows:
        duration = row["duration"]
        duration_ms = duration.total_seconds() * 1000 if duration else 0
        if duration_ms < min_duration_ms:
            continue

        sessions.append({
            "pid": row["pid"],
            "usename": row["usename"],
            "datname": row["datname"],
            "duration_ms": round(duration_ms, 2),
            "state": row["state"],
            "query": row["query"],
        })

        if len(sessions) >= limit:
            break

    return json.dumps({
        "total": len(sessions),
        "sessions": sessions,
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Scenario 8: inspect_table_sizes
# ---------------------------------------------------------------------------
@app.mcp_tool_trigger(
    arg_name="context",
    tool_name="inspect_table_sizes",
    description=(
        "Return storage usage for every user table in the database: estimated "
        "row count, table bytes, index bytes, and total bytes. Sorted by total "
        "size descending. Use this to identify bloated tables (e.g. posts.imgdata "
        "bytea bloat) before optimizing the schema."
    ),
    tool_properties=json.dumps([
        {
            "propertyName": "limit",
            "propertyType": "number",
            "description": "Max number of tables to return (default 50)",
            "isRequired": False,
        },
    ]),
)
def inspect_table_sizes(context: str) -> str:
    args = _parse_args(context)
    limit = max(1, int(args.get("limit") or 50))

    dsn = os.environ.get("ISUCONP_DATABASE_URL")
    if not dsn:
        return json.dumps({"error": "ISUCONP_DATABASE_URL is not set"})

    sizes_sql = """
        SELECT
            schemaname,
            relname AS table_name,
            n_live_tup AS estimated_rows,
            pg_relation_size(relid) AS table_bytes,
            pg_indexes_size(relid) AS index_bytes,
            pg_total_relation_size(relid) AS total_bytes,
            pg_size_pretty(pg_total_relation_size(relid)) AS total_size
        FROM pg_stat_user_tables
        ORDER BY total_bytes DESC
        LIMIT %s
    """

    try:
        with psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor) as conn:
            with conn.cursor() as cur:
                cur.execute("SET statement_timeout = 5000")
                cur.execute(sizes_sql, (limit,))
                rows = cur.fetchall()
    except psycopg2.Error as e:
        return json.dumps({"error": f"DB error: {str(e).strip()}"})

    tables = [
        {
            "schemaname": row["schemaname"],
            "table_name": row["table_name"],
            "estimated_rows": int(row["estimated_rows"] or 0),
            "table_bytes": int(row["table_bytes"] or 0),
            "index_bytes": int(row["index_bytes"] or 0),
            "total_bytes": int(row["total_bytes"] or 0),
            "total_size": row["total_size"],
        }
        for row in rows
    ]

    return json.dumps({
        "total": len(tables),
        "tables": tables,
    }, ensure_ascii=False)
