from flask import Flask, render_template, request, session, redirect, url_for
from datetime import timedelta
from werkzeug.middleware.proxy_fix import ProxyFix
import json
import random
import os
import sqlite3

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.secret_key = "lingua_hero_secret_2025"
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1000)

# ── Visitor tracking ─────────────────────────────────────────────────────────

DB_PATH = "visitors.db"

def init_db():
    """Create the visitors table if it doesn't exist yet."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS visitors (
            ip TEXT PRIMARY KEY,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def record_visitor(ip):
    """Add this IP to the database if we haven't seen it before."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO visitors (ip) VALUES (?)", (ip,))
    conn.commit()
    conn.close()

def get_visitor_count():
    """Return the total number of distinct visitors."""
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM visitors").fetchone()[0]
    conn.close()
    return count

init_db()  # Run once when the app starts

@app.before_request
def track_visitor():
    session.permanent = True
    """Called automatically before every page load."""
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if ip:
        ip = ip.split(",")[0].strip()
    record_visitor(ip)

# ── Load all topic data ──────────────────────────────────────────────────────

def load_topic(language, topic_slug):
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "data", language, f"{topic_slug}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

LANGUAGES = {
    "english": {
        "name": "English",
        "flag": "🇬🇧",
        "topics": [
            {"slug": "irregular-verbs", "name": "Irregular Verbs",  "icon": "🔀", "desc": "200 verbs across 20 levels"},
            {"slug": "phrasal-verbs",   "name": "Phrasal Verbs",    "icon": "➡️", "desc": "Give up, look after, run out..."},
            {"slug": "tenses",          "name": "Verb Tenses",      "icon": "⏱️", "desc": "Present, past, future, perfect"},
            {"slug": "prepositions",    "name": "Prepositions",     "icon": "📍", "desc": "In/on/at, by/with/for"},
            {"slug": "conditionals",    "name": "Conditionals",     "icon": "❓", "desc": "If I were, if I had..."},
            {"slug": "articles",        "name": "Articles",         "icon": "📝", "desc": "A, an, the — when and why"},
        ]
    },
    "german": {
        "name": "Deutsch",
        "flag": "🇩🇪",
        "topics": [
            {"slug": "articles",        "name": "Articles & Gender","icon": "🏷️", "desc": "Der, die, das in all 4 cases"},
            {"slug": "cases",           "name": "Cases",            "icon": "🔄", "desc": "Nominativ, Akkusativ, Dativ, Genitiv"},
            {"slug": "irregular-verbs", "name": "Irregular Verbs",  "icon": "🔀", "desc": "Sein, haben, gehen and more"},
            {"slug": "tenses",          "name": "Verb Tenses",      "icon": "⏱️", "desc": "Präsens, Perfekt, Präteritum"},
            {"slug": "separable-verbs", "name": "Separable Verbs",  "icon": "↔️", "desc": "Aufmachen, anrufen, mitkommen"},
            {"slug": "modal-verbs",     "name": "Modal Verbs",      "icon": "💪", "desc": "Können, müssen, dürfen, wollen"},
        ]
    }
}

PASS_PERCENT = 70

# ── Helpers ──────────────────────────────────────────────────────────────────

def topic_key(language, topic_slug):
    return f"{language}__{topic_slug}"

def get_unlocked(language, topic_slug):
    key = f"unlocked__{topic_key(language, topic_slug)}"
    if key not in session:
        session[key] = [1]
    return session[key]

def get_completed(language, topic_slug):
    key = f"completed__{topic_key(language, topic_slug)}"
    if key not in session:
        session[key] = []
    return session[key]

def mark_completed(language, topic_slug, level_num):
    comp_key = f"completed__{topic_key(language, topic_slug)}"
    unl_key  = f"unlocked__{topic_key(language, topic_slug)}"
    if comp_key not in session:
        session[comp_key] = []
    if unl_key not in session:
        session[unl_key] = [1]
    newly_unlocked = False
    if level_num not in session[comp_key]:
        session[comp_key].append(level_num)
        next_lvl = level_num + 1
        if next_lvl not in session[unl_key]:
            session[unl_key].append(next_lvl)
            newly_unlocked = True
    session.modified = True
    return newly_unlocked

# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("home.html", languages=LANGUAGES, visitors=get_visitor_count())

@app.route("/<language>")
def language_home(language):
    if language not in LANGUAGES:
        return redirect(url_for("home"))
    lang = LANGUAGES[language]
    topics_with_status = []
    for t in lang["topics"]:
        data = load_topic(language, t["slug"])
        t["ready"] = data is not None
        t["total_levels"] = len(data.get("levels", [])) if data else 0
        t["completed"]    = len(get_completed(language, t["slug"])) if data else 0
        topics_with_status.append(t)
    return render_template("language.html", lang=lang, language=language,
                           topics=topics_with_status, visitors=get_visitor_count())

@app.route("/<language>/<topic_slug>")
def topic_home(language, topic_slug):
    if language not in LANGUAGES:
        return redirect(url_for("home"))
    data = load_topic(language, topic_slug)
    if not data:
        return redirect(url_for("language_home", language=language))
    lang       = LANGUAGES[language]
    topic_name = next((t["name"] for t in lang["topics"] if t["slug"] == topic_slug), topic_slug)
    return render_template("topic.html",
        language=language, lang=lang,
        topic_slug=topic_slug, topic_name=topic_name,
        levels=data["levels"],
        unlocked=get_unlocked(language, topic_slug),
        completed=get_completed(language, topic_slug),
        visitors=get_visitor_count())

@app.route("/<language>/<topic_slug>/study/<int:level_num>")
def study(language, topic_slug, level_num):
    if level_num not in get_unlocked(language, topic_slug):
        return redirect(url_for("topic_home", language=language, topic_slug=topic_slug))
    data = load_topic(language, topic_slug)
    level = next((l for l in data["levels"] if l["level"] == level_num), None)
    if not level:
        return redirect(url_for("topic_home", language=language, topic_slug=topic_slug))
    lang       = LANGUAGES[language]
    topic_name = next((t["name"] for t in lang["topics"] if t["slug"] == topic_slug), topic_slug)
    return render_template("study.html",
        language=language, lang=lang,
        topic_slug=topic_slug, topic_name=topic_name,
        level=level, total_levels=len(data["levels"]),
        visitors=get_visitor_count())

@app.route("/<language>/<topic_slug>/play")
def game_play(language, topic_slug):
    level_num = request.args.get("level", "all")
    data = load_topic(language, topic_slug)
    if not data:
        return redirect(url_for("topic_home", language=language, topic_slug=topic_slug))
    if level_num == "all":
        items = [i for l in data["levels"] for i in l["items"]]
    else:
        level = next((l for l in data["levels"] if l["level"] == int(level_num)), None)
        if not level:
            return redirect(url_for("topic_home", language=language, topic_slug=topic_slug))
        items = level["items"]
    random.shuffle(items)
    session.update({"game_items": items, "game_index": 0, "game_score": 0,
                    "game_total": len(items), "game_level": level_num,
                    "game_language": language, "game_topic": topic_slug})
    return redirect(url_for("game_question", language=language, topic_slug=topic_slug))

@app.route("/<language>/<topic_slug>/question", methods=["GET", "POST"])
def game_question(language, topic_slug):
    if "game_items" not in session:
        return redirect(url_for("topic_home", language=language, topic_slug=topic_slug))
    index = session["game_index"]
    items = session["game_items"]
    total = session["game_total"]
    lang  = LANGUAGES[language]
    topic_name = next((t["name"] for t in lang["topics"] if t["slug"] == topic_slug), topic_slug)
    if index >= total:
        return redirect(url_for("game_result", language=language, topic_slug=topic_slug))
    item   = items[index]
    result = None
    user_inputs = []
    if request.method == "POST":
        answers     = item.get("answers", [])
        user_inputs = [request.form.get(f"ans_{i}", "").strip().lower() for i in range(len(answers))]
        if user_inputs == [a.lower() for a in answers]:
            result = "correct"
            session["game_score"] += 1
        else:
            result = "wrong"
        session["game_index"] += 1
        session.modified = True
    return render_template("question.html",
        language=language, lang=lang,
        topic_slug=topic_slug, topic_name=topic_name,
        item=item, result=result, user_inputs=user_inputs,
        index=index + 1, total=total,
        score=session["game_score"],
        visitors=get_visitor_count())

@app.route("/<language>/<topic_slug>/result")
def game_result(language, topic_slug):
    if "game_score" not in session:
        return redirect(url_for("topic_home", language=language, topic_slug=topic_slug))
    score   = session["game_score"]
    total   = session["game_total"]
    level   = session["game_level"]
    percent = int(score / total * 100) if total else 0
    lang    = LANGUAGES[language]
    topic_name = next((t["name"] for t in lang["topics"] if t["slug"] == topic_slug), topic_slug)
    newly_unlocked = False
    if level != "all" and percent >= PASS_PERCENT:
        newly_unlocked = mark_completed(language, topic_slug, int(level))
    for k in ["game_items","game_index","game_score","game_total","game_level","game_language","game_topic"]:
        session.pop(k, None)
    return render_template("result.html",
        language=language, lang=lang,
        topic_slug=topic_slug, topic_name=topic_name,
        score=score, total=total, level=level,
        percent=percent, newly_unlocked=newly_unlocked,
        visitors=get_visitor_count())

if __name__ == "__main__":
    app.run(debug=True)
