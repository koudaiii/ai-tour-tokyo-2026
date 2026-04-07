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

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

logger = logging.getLogger(__name__)

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8080")


def _api_get(path: str, params: dict | None = None) -> dict:
    url = f"{API_BASE_URL}{path}"
    if params:
        filtered = {k: v for k, v in params.items() if v is not None}
        if filtered:
            url += "?" + urllib.parse.urlencode(filtered)
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Scenario 1: browse_timeline
#   Combines: GET /api/posts (with pagination)
#   Value-add: Summarises the timeline into a digest format with engagement
#   metrics, filters by keyword, and supports natural cursor-based pagination.
# ---------------------------------------------------------------------------
@app.function_name("browse_timeline")
@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="browse_timeline",
    description=(
        "Browse the social media timeline. Returns a digest of recent posts "
        "with engagement metrics (comment counts). Supports keyword filtering "
        "and cursor-based pagination. Use this as the starting point to "
        "understand what is happening on the platform."
    ),
    toolProperties=json.dumps({
        "keyword": {
            "type": "string",
            "description": "Optional keyword to filter posts (searches post body text)",
        },
        "max_created_at": {
            "type": "string",
            "description": "ISO8601 cursor for pagination — fetch posts older than this timestamp",
        },
        "limit": {
            "type": "number",
            "description": "Max number of posts to return (default 10, max 20)",
        },
    }),
)
def browse_timeline(context: str) -> str:
    args = json.loads(context)
    keyword = (args.get("keyword") or "").lower()
    limit = min(int(args.get("limit") or 10), 20)

    params = {}
    if args.get("max_created_at"):
        params["max_created_at"] = args["max_created_at"]

    try:
        data = _api_get("/api/posts", params)
    except urllib.error.HTTPError as e:
        return json.dumps({"error": f"API error: {e.code}"})

    posts = data.get("posts", [])

    if keyword:
        posts = [p for p in posts if keyword in (p.get("body") or "").lower()]

    posts = posts[:limit]

    digest = []
    for p in posts:
        digest.append({
            "id": p["id"],
            "author": p["user"]["account_name"],
            "body_preview": (p["body"] or "")[:120],
            "image_url": p.get("image_url"),
            "comment_count": p["comment_count"],
            "latest_commenters": list({
                c["user"]["account_name"] for c in (p.get("comments") or [])
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
#   Combines: GET /api/users/{name} + GET /api/users/{name}/posts
#   Value-add: Single call returns full user profile, activity stats,
#   and recent posts — a complete picture of who a user is.
# ---------------------------------------------------------------------------
@app.function_name("explore_user")
@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="explore_user",
    description=(
        "Get a comprehensive view of a user: profile, activity statistics, "
        "and their recent posts with comments — all in a single call. "
        "Use this to understand who a user is and what they have been posting."
    ),
    toolProperties=json.dumps({
        "account_name": {
            "type": "string",
            "description": "The account name of the user to explore",
        },
    }),
    toolInputRequired='["account_name"]',
)
def explore_user(context: str) -> str:
    args = json.loads(context)
    account_name = args.get("account_name")
    if not account_name:
        return json.dumps({"error": "account_name is required"})

    safe_name = urllib.parse.quote(account_name)

    try:
        profile = _api_get(f"/api/users/{safe_name}")
    except urllib.error.HTTPError as e:
        return json.dumps({"error": f"User not found or API error: {e.code}"})

    try:
        posts_data = _api_get(f"/api/users/{safe_name}/posts")
    except urllib.error.HTTPError:
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
#   Combines: GET /api/posts (potentially multiple pages)
#   Value-add: Sorts by engagement (comment_count) — the raw API only
#   supports chronological order. Identifies trending content.
# ---------------------------------------------------------------------------
@app.function_name("find_popular_posts")
@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="find_popular_posts",
    description=(
        "Find the most popular (most commented) posts on the platform. "
        "The API only returns posts in chronological order, but this tool "
        "re-ranks them by engagement. Use this to discover trending content."
    ),
    toolProperties=json.dumps({
        "min_comments": {
            "type": "number",
            "description": "Only return posts with at least this many comments (default 1)",
        },
        "limit": {
            "type": "number",
            "description": "Max number of posts to return (default 5, max 20)",
        },
    }),
)
def find_popular_posts(context: str) -> str:
    args = json.loads(context)
    min_comments = int(args.get("min_comments") or 1)
    limit = min(int(args.get("limit") or 5), 20)

    try:
        data = _api_get("/api/posts")
    except urllib.error.HTTPError as e:
        return json.dumps({"error": f"API error: {e.code}"})

    posts = data.get("posts", [])
    posts = [p for p in posts if p.get("comment_count", 0) >= min_comments]
    posts.sort(key=lambda p: p.get("comment_count", 0), reverse=True)
    posts = posts[:limit]

    results = []
    for p in posts:
        results.append({
            "id": p["id"],
            "author": p["user"]["account_name"],
            "body_preview": (p["body"] or "")[:120],
            "image_url": p.get("image_url"),
            "comment_count": p["comment_count"],
            "commenters": list({
                c["user"]["account_name"] for c in (p.get("comments") or [])
            }),
            "created_at": p["created_at"],
        })

    return json.dumps({
        "total": len(results),
        "posts": results,
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Scenario 4: get_conversation
#   Combines: GET /api/posts/{id} (with all_comments=True via the detail endpoint)
#   Value-add: Formats the post + comment thread as a human-readable
#   conversation transcript. Much easier for an LLM to reason about
#   than raw JSON.
# ---------------------------------------------------------------------------
@app.function_name("get_conversation")
@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="get_conversation",
    description=(
        "Get a post and its full comment thread formatted as a readable "
        "conversation. Returns the original post followed by all comments "
        "in chronological order, making it easy to follow the discussion."
    ),
    toolProperties=json.dumps({
        "post_id": {
            "type": "number",
            "description": "The ID of the post to view the conversation for",
        },
    }),
    toolInputRequired='["post_id"]',
)
def get_conversation(context: str) -> str:
    args = json.loads(context)
    post_id = args.get("post_id")
    if not post_id:
        return json.dumps({"error": "post_id is required"})

    try:
        data = _api_get(f"/api/posts/{int(post_id)}")
    except urllib.error.HTTPError as e:
        return json.dumps({"error": f"API error: {e.code}"})

    post = data.get("post")
    if not post:
        return json.dumps({"error": "post not found"})

    thread = []
    thread.append({
        "type": "post",
        "author": post["user"]["account_name"],
        "body": post["body"],
        "image_url": post.get("image_url"),
        "created_at": post["created_at"],
    })

    for c in post.get("comments", []):
        thread.append({
            "type": "comment",
            "author": c["user"]["account_name"],
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
#   Combines: GET /api/users/{name} for multiple users
#   Value-add: Fetches profiles in sequence and presents a side-by-side
#   comparison table. APIM cannot orchestrate multi-call aggregation.
# ---------------------------------------------------------------------------
@app.function_name("compare_users")
@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="compare_users",
    description=(
        "Compare activity statistics of two or more users side by side. "
        "Shows post counts, comment counts, and engagement metrics for each "
        "user. Useful for understanding relative activity levels."
    ),
    toolProperties=json.dumps({
        "account_names": {
            "type": "string",
            "description": "Comma-separated list of account names to compare (2-5 users)",
        },
    }),
    toolInputRequired='["account_names"]',
)
def compare_users(context: str) -> str:
    args = json.loads(context)
    raw = args.get("account_names", "")
    names = [n.strip() for n in raw.split(",") if n.strip()]

    if len(names) < 2:
        return json.dumps({"error": "Provide at least 2 account names separated by commas"})
    if len(names) > 5:
        names = names[:5]

    comparisons = []
    for name in names:
        safe = urllib.parse.quote(name)
        try:
            profile = _api_get(f"/api/users/{safe}")
            comparisons.append({
                "account_name": name,
                "post_count": profile.get("post_count", 0),
                "comment_count": profile.get("comment_count", 0),
                "commented_count": profile.get("commented_count", 0),
                "created_at": profile.get("user", {}).get("created_at"),
            })
        except urllib.error.HTTPError:
            comparisons.append({
                "account_name": name,
                "error": "user not found",
            })

    return json.dumps({
        "users": comparisons,
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Scenario 6: search_posts
#   Combines: GET /api/posts (multiple pages via cursor)
#   Value-add: The API has no search — this tool fetches the timeline and
#   filters client-side by keyword across body and commenter names.
#   APIM cannot add search semantics to an API that lacks them.
# ---------------------------------------------------------------------------
@app.function_name("search_posts")
@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="search_posts",
    description=(
        "Search posts by keyword. The underlying API has no search endpoint, "
        "so this tool fetches recent posts and filters them by matching "
        "the keyword against post body text and commenter names. "
        "Returns matching posts ranked by relevance."
    ),
    toolProperties=json.dumps({
        "query": {
            "type": "string",
            "description": "Search keyword or phrase to look for in post body and comments",
        },
        "limit": {
            "type": "number",
            "description": "Max results to return (default 5, max 20)",
        },
    }),
    toolInputRequired='["query"]',
)
def search_posts(context: str) -> str:
    args = json.loads(context)
    query = (args.get("query") or "").lower()
    if not query:
        return json.dumps({"error": "query is required"})

    limit = min(int(args.get("limit") or 5), 20)

    try:
        data = _api_get("/api/posts")
    except urllib.error.HTTPError as e:
        return json.dumps({"error": f"API error: {e.code}"})

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
            commenter = (c.get("user", {}).get("account_name") or "").lower()
            if query in commenter:
                score += 1

        author = (p.get("user", {}).get("account_name") or "").lower()
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
            "author": p["user"]["account_name"],
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
