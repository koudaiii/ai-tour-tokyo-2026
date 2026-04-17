import datetime
import logging
import os
import pathlib
import re
import shlex
import subprocess
import tempfile
import uuid

import flask
import psycopg2
import psycopg2.extras
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from dotenv import load_dotenv
from flask_session import Session
from jinja2 import pass_eval_context
from markupsafe import Markup, escape
from pymemcache.client.base import Client as MemcacheClient

UPLOAD_LIMIT = 10 * 1024 * 1024  # 10mb
POSTS_PER_PAGE = 20

load_dotenv()

# Configure Azure Monitor / Application Insights
_appinsights_conn_str = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
if _appinsights_conn_str:
    from azure.monitor.opentelemetry import configure_azure_monitor
    configure_azure_monitor(connection_string=_appinsights_conn_str)

AZURE_STORAGE_CONTAINER_NAME = os.environ.get("AZURE_STORAGE_CONTAINER_NAME", "images")

_blob_service_client = None


def blob_service_client():
    global _blob_service_client
    if _blob_service_client is not None:
        return _blob_service_client

    conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    account_url = os.environ.get("AZURE_STORAGE_ACCOUNT_URL")

    if conn_str:
        _blob_service_client = BlobServiceClient.from_connection_string(conn_str)
    elif account_url:
        _blob_service_client = BlobServiceClient(account_url, credential=DefaultAzureCredential())

    return _blob_service_client


def blob_container_client():
    client = blob_service_client()
    if client is None:
        return None
    return client.get_container_client(AZURE_STORAGE_CONTAINER_NAME)


def _mime_to_ext(mime):
    if mime == "image/jpeg":
        return ".jpg"
    elif mime == "image/png":
        return ".png"
    elif mime == "image/gif":
        return ".gif"
    return ""


def get_blob_url(blob_key):
    client = blob_service_client()
    if client is None:
        return None
    return f"{client.url}{AZURE_STORAGE_CONTAINER_NAME}/{blob_key}"


_config = None
logger = logging.getLogger(__name__)


def config():
    global _config
    if _config is None:
        database_url = os.environ.get(
            "ISUCONP_DATABASE_URL",
            "postgresql://isuconp:isuconp@127.0.0.1:5432/isuconp?sslmode=disable",
        )
        db_conf = {"dsn": database_url}
        logger.info("Using DB via ISUCONP_DATABASE_URL")

        _config = {
            "db": db_conf,
            "memcache": {
                "address": os.environ.get(
                    "ISUCONP_MEMCACHED_ADDRESS", "127.0.0.1:11211"
                ),
            },
        }
        logger.info("Using Memcached %s", _config["memcache"]["address"])
    return _config


_db = None


def db():
    global _db
    if _db is None:
        conf = config()["db"].copy()
        _db = psycopg2.connect(
            cursor_factory=psycopg2.extras.RealDictCursor,
            **conf,
        )
        _db.autocommit = True
    return _db


def db_initialize():
    cur = db().cursor()
    sqls = [
        "DELETE FROM users WHERE id > 1000",
        "DELETE FROM posts WHERE id > 10000",
        "DELETE FROM comments WHERE id > 100000",
        "UPDATE users SET del_flg = 0",
        "UPDATE users SET del_flg = 1 WHERE id % 50 = 0",
    ]
    for q in sqls:
        cur.execute(q)


_mcclient = None


def memcache():
    global _mcclient
    if _mcclient is None:
        conf = config()["memcache"]
        _mcclient = MemcacheClient(
            conf["address"], no_delay=True, default_noreply=False
        )
    return _mcclient


def try_login(account_id, password):
    cur = db().cursor()
    cur.execute(
        "SELECT * FROM users WHERE account_id = %s AND del_flg = 0", (account_id,)
    )
    user = cur.fetchone()

    if user and calculate_passhash(user["account_id"], password) == user["passhash"]:
        return user
    return None


def validate_user(account_id: str, password: str):
    if not re.fullmatch(r"[0-9a-zA-Z_]{3,}", account_id):
        return False
    if not re.fullmatch(r"[0-9a-zA-Z_]{6,}", password):
        return False
    return True


def digest(src: str):
    # opensslのバージョンによっては (stdin)= というのがつくので取る
    out = subprocess.check_output(
        f"printf %s {shlex.quote(src)} | openssl dgst -sha512 | sed 's/^.*= //'",
        shell=True,
        encoding="utf-8",
    )
    return out.strip()


def calculate_salt(account_id: str):
    return digest(account_id)


def calculate_passhash(account_id: str, password: str):
    return digest("%s:%s" % (password, calculate_salt(account_id)))


def get_session_user():
    user = flask.session.get("user")
    if user:
        cur = db().cursor()
        cur.execute("SELECT * FROM users WHERE id = %s", (user["id"],))
        return cur.fetchone()
    return None


def make_posts(results, all_comments=False):
    posts = []
    cursor = db().cursor()
    for post in results:
        cursor.execute(
            "SELECT COUNT(*) AS count FROM comments WHERE post_id = %s",
            (post["id"],),
        )
        post["comment_count"] = cursor.fetchone()["count"]

        query = (
            "SELECT * FROM comments WHERE post_id = %s ORDER BY created_at DESC"
        )
        if not all_comments:
            query += " LIMIT 3"

        cursor.execute(query, (post["id"],))
        comments = list(cursor)
        for comment in comments:
            cursor.execute(
                "SELECT * FROM users WHERE id = %s", (comment["user_id"],)
            )
            comment["user"] = cursor.fetchone()
        comments.reverse()
        post["comments"] = comments

        cursor.execute("SELECT * FROM users WHERE id = %s", (post["user_id"],))
        post["user"] = cursor.fetchone()

        if not post["user"]["del_flg"]:
            posts.append(post)

        if len(posts) >= POSTS_PER_PAGE:
            break
    return posts


# app setup
root_dir = pathlib.Path(__file__).resolve().parent
public_dir = root_dir / "public"
app = flask.Flask(__name__, static_folder=str(public_dir), static_url_path="")
# app.debug = True

# Flask-Session
app.config["SESSION_TYPE"] = "memcached"
app.config["SESSION_MEMCACHED"] = memcache()
Session(app)


@app.template_global()
def image_url(post):
    blob_key = post.get("img_blob_key")
    if blob_key:
        blob_url = get_blob_url(blob_key)
        if blob_url:
            return blob_url

    ext = _mime_to_ext(post["mime"])
    return "/image/%s%s" % (post["id"], ext)


# http://flask.pocoo.org/snippets/28/
_paragraph_re = re.compile(r"(?:\r\n|\r|\n){2,}")


@app.template_filter()
@pass_eval_context
def nl2br(eval_ctx, value):
    result = "\n\n".join(
        "<p>%s</p>" % p.replace("\n", "<br>\n")
        for p in _paragraph_re.split(escape(value))
    )
    if eval_ctx.autoescape:
        result = Markup(result)
    return result


# endpoints


@app.route("/initialize")
def get_initialize():
    db_initialize()
    return ""


@app.route("/health")
def get_health():
    return flask.jsonify({"status": "ok"}), 200


@app.route("/public/<path:filename>")
def get_public_file(filename):
    # nginx がないローカル実行時向けフォールバック。
    return flask.send_from_directory(str(public_dir), filename)


@app.route("/login")
def get_login():
    if get_session_user():
        return flask.redirect("/")
    return flask.render_template("login.html", me=None)


@app.route("/login", methods=["POST"])
def post_login():
    if get_session_user():
        return flask.redirect("/")

    user = try_login(flask.request.form["account_id"], flask.request.form["password"])
    if user:
        flask.session["user"] = {"id": user["id"]}
        flask.session["csrf_token"] = os.urandom(16).hex()
        return flask.redirect("/")

    flask.flash("アカウントIDかパスワードが間違っています")
    return flask.redirect("/login")


@app.route("/register")
def get_register():
    if get_session_user():
        return flask.redirect("/")
    return flask.render_template("register.html", me=None)


@app.route("/register", methods=["POST"])
def post_register():
    if get_session_user():
        return flask.redirect("/")

    account_id = flask.request.form["account_id"]
    password = flask.request.form["password"]
    if not validate_user(account_id, password):
        flask.flash(
            "アカウントIDは3文字以上、パスワードは6文字以上である必要があります"
        )
        return flask.redirect("/register")

    cursor = db().cursor()
    cursor.execute("SELECT 1 FROM users WHERE account_id = %s", (account_id,))
    user = cursor.fetchone()
    if user:
        flask.flash("アカウントIDがすでに使われています")
        return flask.redirect("/register")

    query = "INSERT INTO users (account_id, passhash) VALUES (%s, %s) RETURNING id"
    cursor.execute(query, (account_id, calculate_passhash(account_id, password)))

    flask.session["user"] = {"id": cursor.fetchone()["id"]}
    flask.session["csrf_token"] = os.urandom(16).hex()
    return flask.redirect("/")


@app.route("/logout")
def get_logout():
    flask.session.clear()
    return flask.redirect("/")


@app.route("/")
def get_index():
    me = get_session_user()

    cursor = db().cursor()
    cursor.execute(
        "SELECT id, user_id, body, created_at, mime FROM posts ORDER BY created_at DESC"
    )
    posts = make_posts(cursor.fetchall())

    return flask.render_template("index.html", posts=posts, me=me)


@app.route("/@<account_id>")
def get_user_list(account_id):
    cursor = db().cursor()

    cursor.execute(
        "SELECT * FROM users WHERE account_id = %s AND del_flg = 0",
        (account_id,),
    )
    user = cursor.fetchone()
    if user is None:
        flask.abort(404)  # raises exception

    cursor.execute(
        "SELECT id, user_id, body, mime, created_at FROM posts WHERE user_id = %s ORDER BY created_at DESC",
        (user["id"],),
    )
    posts = make_posts(cursor.fetchall())

    cursor.execute(
        "SELECT COUNT(*) AS count FROM comments WHERE user_id = %s", (user["id"],)
    )
    comment_count = cursor.fetchone()["count"]

    cursor.execute("SELECT id FROM posts WHERE user_id = %s", (user["id"],))
    post_ids = [p["id"] for p in cursor]
    post_count = len(post_ids)

    commented_count = 0
    if post_count > 0:
        cursor.execute(
            "SELECT COUNT(*) AS count FROM comments WHERE post_id = ANY(%s)",
            (post_ids,),
        )
        commented_count = cursor.fetchone()["count"]

    me = get_session_user()

    return flask.render_template(
        "user.html",
        posts=posts,
        user=user,
        post_count=post_count,
        comment_count=comment_count,
        commented_count=commented_count,
        me=me,
    )


def _parse_iso8601(s):
    # http://bugs.python.org/issue15873
    # Ignore timezone
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})[ tT](\d{2}):(\d{2}):(\d{2}).*", s)
    if not m:
        raise ValueError("Invlaid iso8601 format: %r" % (s,))
    return datetime.datetime(*map(int, m.groups()))


@app.route("/posts")
def get_posts():
    cursor = db().cursor()
    max_created_at = flask.request.args.get("max_created_at")
    if not max_created_at:
        return ""

    max_created_at = _parse_iso8601(max_created_at)
    cursor.execute(
        "SELECT id, user_id, body, mime, created_at FROM posts WHERE created_at <= %s ORDER BY created_at DESC",
        (max_created_at,),
    )
    results = cursor.fetchall()
    posts = make_posts(results)
    return flask.render_template("posts.html", posts=posts)


@app.route("/posts/<id>")
def get_posts_id(id):
    cursor = db().cursor()

    cursor.execute("SELECT * FROM posts WHERE id = %s", (id,))
    posts = make_posts(cursor.fetchall(), all_comments=True)
    if not posts:
        flask.abort(404)

    me = get_session_user()
    return flask.render_template("post.html", post=posts[0], me=me)


@app.route("/", methods=["POST"])
def post_index():
    me = get_session_user()
    if not me:
        return flask.redirect("/login")

    if flask.request.form["csrf_token"] != flask.session["csrf_token"]:
        flask.abort(422)

    file = flask.request.files.get("file")
    if not file:
        flask.flash("画像が必要です")
        return flask.redirect("/")

    # 投稿のContent-Typeからファイルのタイプを決定する
    mime = file.mimetype
    if mime not in ("image/jpeg", "image/png", "image/gif"):
        flask.flash("投稿できる画像形式はjpgとpngとgifだけです")
        return flask.redirect("/")

    with tempfile.TemporaryFile() as tempf:
        file.save(tempf)
        tempf.flush()

        if tempf.tell() > UPLOAD_LIMIT:
            flask.flash("ファイルサイズが大きすぎます")
            return flask.redirect("/")

        tempf.seek(0)
        imgdata = tempf.read()

    container = blob_container_client()
    cursor = db().cursor()

    if container:
        try:
            blob_key = f"{uuid.uuid4()}{_mime_to_ext(mime)}"
            container.upload_blob(
                blob_key,
                imgdata,
                content_settings=ContentSettings(content_type=mime),
                overwrite=True,
            )
            query = "INSERT INTO posts (user_id, mime, imgdata, body, img_blob_key) VALUES (%s,%s,%s,%s,%s) RETURNING id"
            cursor.execute(query, (me["id"], mime, b"", flask.request.form.get("body"), blob_key))
        except Exception:
            app.logger.exception("Blob upload failed. Falling back to DB imgdata storage.")
            query = "INSERT INTO posts (user_id, mime, imgdata, body) VALUES (%s,%s,%s,%s) RETURNING id"
            cursor.execute(query, (me["id"], mime, imgdata, flask.request.form.get("body")))
    else:
        query = "INSERT INTO posts (user_id, mime, imgdata, body) VALUES (%s,%s,%s,%s) RETURNING id"
        cursor.execute(query, (me["id"], mime, imgdata, flask.request.form.get("body")))

    pid = cursor.fetchone()["id"]
    return flask.redirect("/posts/%d" % pid)


@app.route("/image/<id>.<ext>")
def get_image(id, ext):
    if not id:
        return ""
    id = int(id)
    if id == 0:
        return ""

    cursor = db().cursor()
    cursor.execute("SELECT * FROM posts WHERE id = %s", (id,))
    post = cursor.fetchone()

    blob_key = post.get("img_blob_key")
    if blob_key:
        blob_url = get_blob_url(blob_key)
        if blob_url:
            return flask.redirect(blob_url)

    mime = post["mime"]
    if (
        ext == "jpg"
        and mime == "image/jpeg"
        or ext == "png"
        and mime == "image/png"
        or ext == "gif"
        and mime == "image/gif"
    ):
        return flask.Response(bytes(post["imgdata"]), mimetype=mime)

    flask.abort(404)


@app.route("/comment", methods=["POST"])
def post_comment():
    me = get_session_user()
    if not me:
        return flask.redirect("/login")

    if flask.request.form["csrf_token"] != flask.session["csrf_token"]:
        flask.abort(422)

    post_id = flask.request.form["post_id"]
    if not re.match(r"[0-9]+", post_id):
        return "post_idは整数のみです"
    post_id = int(post_id)

    query = (
        "INSERT INTO comments (post_id, user_id, comment) VALUES (%s, %s, %s)"
    )
    cursor = db().cursor()
    cursor.execute(query, (post_id, me["id"], flask.request.form["comment"]))

    return flask.redirect("/posts/%d" % post_id)


@app.route("/admin/banned")
def get_banned():
    me = get_session_user()
    if not me:
        return flask.redirect("/login")

    if me["authority"] == 0:
        flask.abort(403)

    cursor = db().cursor()
    cursor.execute(
        "SELECT * FROM users WHERE authority = 0 AND del_flg = 0 ORDER BY created_at DESC"
    )
    users = cursor.fetchall()

    flask.render_template("banned.html", users=users, me=me)


@app.route("/admin/banned", methods=["POST"])
def post_banned():
    me = get_session_user()
    if not me:
        return flask.redirect("/login")

    if me["authority"] == 0:
        flask.abort(403)

    if flask.request.form["csrf_token"] != flask.session["csrf_token"]:
        flask.abort(422)

    cursor = db().cursor()
    query = "UPDATE users SET del_flg = %s WHERE id = %s"
    for id in flask.request.form.getlist("uid", type=int):
        cursor.execute(query, (1, id))

    return flask.redirect("/admin/banned")


# ---- JSON API helpers ----


def _image_url_for_post(post):
    blob_key = post.get("img_blob_key")
    if blob_key:
        blob_url = get_blob_url(blob_key)
        if blob_url:
            return blob_url
    ext = _mime_to_ext(post["mime"])
    return "/image/%s%s" % (post["id"], ext)


def _post_to_dict(post):
    return {
        "id": post["id"],
        "user": {
            "id": post["user"]["id"],
            "account_id": post["user"]["account_id"],
        },
        "body": post["body"],
        "mime": post["mime"],
        "image_url": _image_url_for_post(post),
        "created_at": post["created_at"].isoformat(),
        "comment_count": post["comment_count"],
        "comments": [
            {
                "id": c["id"],
                "comment": c["comment"],
                "user": {
                    "id": c["user"]["id"],
                    "account_id": c["user"]["account_id"],
                },
                "created_at": c["created_at"].isoformat(),
            }
            for c in post["comments"]
        ],
    }


def _get_user_or_404(account_id):
    cursor = db().cursor()
    cursor.execute(
        "SELECT * FROM users WHERE account_id = %s AND del_flg = 0",
        (account_id,),
    )
    return cursor.fetchone()


# ---- JSON API endpoints ----


@app.route("/api/posts")
def api_get_posts():
    cursor = db().cursor()
    max_created_at = flask.request.args.get("max_created_at")
    if max_created_at:
        max_created_at = _parse_iso8601(max_created_at)
        cursor.execute(
            "SELECT id, user_id, body, mime, created_at FROM posts WHERE created_at <= %s ORDER BY created_at DESC",
            (max_created_at,),
        )
    else:
        cursor.execute(
            "SELECT id, user_id, body, mime, created_at FROM posts ORDER BY created_at DESC"
        )
    posts = make_posts(cursor.fetchall())
    return flask.jsonify({"posts": [_post_to_dict(p) for p in posts]})


@app.route("/api/posts/<int:id>")
def api_get_post(id):
    cursor = db().cursor()
    cursor.execute("SELECT * FROM posts WHERE id = %s", (id,))
    posts = make_posts(cursor.fetchall(), all_comments=True)
    if not posts:
        return flask.jsonify({"error": "not found"}), 404
    return flask.jsonify({"post": _post_to_dict(posts[0])})


@app.route("/api/posts", methods=["POST"])
def api_create_post():
    me = get_session_user()
    if not me:
        return flask.jsonify({"error": "login required"}), 401

    if flask.request.form.get("csrf_token") != flask.session.get("csrf_token"):
        return flask.jsonify({"error": "invalid csrf_token"}), 422

    file = flask.request.files.get("file")
    if not file:
        return flask.jsonify({"error": "file is required"}), 400

    mime = file.mimetype
    if mime not in ("image/jpeg", "image/png", "image/gif"):
        return flask.jsonify({"error": "unsupported image format"}), 400

    with tempfile.TemporaryFile() as tempf:
        file.save(tempf)
        tempf.flush()
        if tempf.tell() > UPLOAD_LIMIT:
            return flask.jsonify({"error": "file too large"}), 400
        tempf.seek(0)
        imgdata = tempf.read()

    container = blob_container_client()
    cursor = db().cursor()

    if container:
        try:
            blob_key = f"{uuid.uuid4()}{_mime_to_ext(mime)}"
            container.upload_blob(
                blob_key,
                imgdata,
                content_settings=ContentSettings(content_type=mime),
                overwrite=True,
            )
            query = "INSERT INTO posts (user_id, mime, imgdata, body, img_blob_key) VALUES (%s,%s,%s,%s,%s) RETURNING id"
            cursor.execute(query, (me["id"], mime, b"", flask.request.form.get("body"), blob_key))
        except Exception:
            app.logger.exception("Blob upload failed. Falling back to DB imgdata storage.")
            query = "INSERT INTO posts (user_id, mime, imgdata, body) VALUES (%s,%s,%s,%s) RETURNING id"
            cursor.execute(query, (me["id"], mime, imgdata, flask.request.form.get("body")))
    else:
        query = "INSERT INTO posts (user_id, mime, imgdata, body) VALUES (%s,%s,%s,%s) RETURNING id"
        cursor.execute(query, (me["id"], mime, imgdata, flask.request.form.get("body")))

    pid = cursor.fetchone()["id"]
    return flask.jsonify({"id": pid}), 201


@app.route("/api/comments", methods=["POST"])
def api_create_comment():
    me = get_session_user()
    if not me:
        return flask.jsonify({"error": "login required"}), 401

    data = flask.request.get_json(silent=True) or {}
    if data.get("csrf_token") != flask.session.get("csrf_token"):
        return flask.jsonify({"error": "invalid csrf_token"}), 422

    post_id = data.get("post_id")
    comment = data.get("comment")
    if not post_id or not isinstance(post_id, int):
        return flask.jsonify({"error": "post_id must be an integer"}), 400
    if not comment:
        return flask.jsonify({"error": "comment is required"}), 400

    cursor = db().cursor()
    cursor.execute(
        "INSERT INTO comments (post_id, user_id, comment) VALUES (%s, %s, %s)",
        (post_id, me["id"], comment),
    )
    return flask.jsonify({"post_id": post_id}), 201


@app.route("/api/users")
def api_get_users():
    cursor = db().cursor()
    cursor.execute(
        "SELECT id, account_id, created_at FROM users WHERE del_flg = 0 ORDER BY created_at DESC"
    )
    users = [
        {
            "id": u["id"],
            "account_id": u["account_id"],
            "created_at": u["created_at"].isoformat(),
        }
        for u in cursor.fetchall()
    ]
    return flask.jsonify({"users": users})


@app.route("/api/users/<account_id>")
def api_get_user(account_id):
    user = _get_user_or_404(account_id)
    if user is None:
        return flask.jsonify({"error": "not found"}), 404

    cursor = db().cursor()

    cursor.execute(
        "SELECT COUNT(*) AS count FROM comments WHERE user_id = %s", (user["id"],)
    )
    comment_count = cursor.fetchone()["count"]

    cursor.execute("SELECT id FROM posts WHERE user_id = %s", (user["id"],))
    post_ids = [p["id"] for p in cursor]
    post_count = len(post_ids)

    commented_count = 0
    if post_count > 0:
        cursor.execute(
            "SELECT COUNT(*) AS count FROM comments WHERE post_id = ANY(%s)",
            (post_ids,),
        )
        commented_count = cursor.fetchone()["count"]

    return flask.jsonify({
        "user": {
            "id": user["id"],
            "account_id": user["account_id"],
            "created_at": user["created_at"].isoformat(),
        },
        "post_count": post_count,
        "comment_count": comment_count,
        "commented_count": commented_count,
    })


@app.route("/api/users/<account_id>/posts")
def api_get_user_posts(account_id):
    user = _get_user_or_404(account_id)
    if user is None:
        return flask.jsonify({"error": "not found"}), 404

    cursor = db().cursor()
    cursor.execute(
        "SELECT id, user_id, body, mime, created_at FROM posts WHERE user_id = %s ORDER BY created_at DESC",
        (user["id"],),
    )
    posts = make_posts(cursor.fetchall())
    return flask.jsonify({"posts": [_post_to_dict(p) for p in posts]})


@app.route("/api/users/<account_id>/posts/<int:id>")
def api_get_user_post(account_id, id):
    user = _get_user_or_404(account_id)
    if user is None:
        return flask.jsonify({"error": "not found"}), 404

    cursor = db().cursor()
    cursor.execute(
        "SELECT * FROM posts WHERE id = %s AND user_id = %s", (id, user["id"])
    )
    posts = make_posts(cursor.fetchall(), all_comments=True)
    if not posts:
        return flask.jsonify({"error": "not found"}), 404
    return flask.jsonify({"post": _post_to_dict(posts[0])})
