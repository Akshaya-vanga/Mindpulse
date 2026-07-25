"""
MindPulse backend
------------------
Flask + SQLite API that gives the existing MindPulse front-end (mood.html,
focus.html, iq.html, etc.) a place to save results, plus a dashboard and
a small analytics layer on top of the saved data.

Run:
    pip install -r requirements.txt
    python app.py
Then open http://localhost:5000/
"""

from flask import Flask, request, jsonify, send_from_directory
import sqlite3
import os
import datetime

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "mindpulse.db")
PUBLIC_DIR = os.path.join(BASE_DIR, "public")

app = Flask(__name__, static_folder=PUBLIC_DIR, static_url_path="")

VALID_TEST_TYPES = {
    "mood", "focus", "memory", "decision", "personality",
    "iq", "color", "sequence", "games",
}


# --------------------------------------------------------------------------
# DB helpers
# --------------------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            test_type TEXT NOT NULL,
            score REAL NOT NULL,
            max_score REAL,
            label TEXT,
            time_taken_sec INTEGER,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
# Static pages (serves the existing MindPulse front-end untouched)
# --------------------------------------------------------------------------
@app.route("/")
def home():
    return send_from_directory(PUBLIC_DIR, "selection.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(PUBLIC_DIR, filename)


# --------------------------------------------------------------------------
# API: save a result
# --------------------------------------------------------------------------
@app.route("/api/results", methods=["POST"])
def save_result():
    data = request.get_json(silent=True) or {}

    user_id = str(data.get("user_id", "")).strip()
    test_type = str(data.get("test_type", "")).strip().lower()
    score = data.get("score")
    max_score = data.get("max_score")
    label = data.get("label")
    time_taken_sec = data.get("time_taken_sec")

    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    if test_type not in VALID_TEST_TYPES:
        return jsonify({"error": f"test_type must be one of {sorted(VALID_TEST_TYPES)}"}), 400
    if score is None:
        return jsonify({"error": "score is required"}), 400

    conn = get_conn()
    conn.execute(
        """
        INSERT INTO results (user_id, test_type, score, max_score, label, time_taken_sec, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id, test_type, float(score),
            float(max_score) if max_score is not None else None,
            label,
            int(time_taken_sec) if time_taken_sec is not None else None,
            datetime.datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"}), 201


# --------------------------------------------------------------------------
# API: raw history for one user
# --------------------------------------------------------------------------
@app.route("/api/results/<user_id>", methods=["GET"])
def get_results(user_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM results WHERE user_id = ? ORDER BY created_at ASC",
        (user_id,),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# --------------------------------------------------------------------------
# API: per-test summary (count, avg, trend) for one user
# --------------------------------------------------------------------------
@app.route("/api/summary/<user_id>", methods=["GET"])
def summary(user_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM results WHERE user_id = ? ORDER BY created_at ASC",
        (user_id,),
    ).fetchall()
    conn.close()

    if not rows:
        return jsonify({})

    df = pd.DataFrame([dict(r) for r in rows])
    out = {}
    for test_type, group in df.groupby("test_type"):
        group = group.sort_values("created_at")
        first_score = float(group.iloc[0]["score"])
        last_score = float(group.iloc[-1]["score"])
        out[test_type] = {
            "attempts": int(len(group)),
            "avg_score": round(float(group["score"].mean()), 2),
            "best_score": float(group["score"].max()),
            "latest_score": last_score,
            "latest_label": group.iloc[-1]["label"],
            "trend": round(last_score - first_score, 2),
            "history": [
                {"created_at": r["created_at"], "score": r["score"], "label": r["label"]}
                for _, r in group.iterrows()
            ],
        }
    return jsonify(out)


# --------------------------------------------------------------------------
# API: insights — correlations for this user, logistic regression across
# the whole dataset once there's enough data to make it meaningful.
# --------------------------------------------------------------------------
@app.route("/api/insights/<user_id>", methods=["GET"])
def insights(user_id):
    conn = get_conn()
    user_rows = conn.execute(
        "SELECT * FROM results WHERE user_id = ? ORDER BY created_at ASC",
        (user_id,),
    ).fetchall()
    all_rows = conn.execute("SELECT * FROM results").fetchall()
    conn.close()

    result = {"correlations": [], "risk_model": None}

    if not user_rows:
        return jsonify(result)

    df = pd.DataFrame([dict(r) for r in user_rows])

    # --- Within-user correlation between pairs of test types -----------
    # Align by attempt order (1st mood attempt with 1st focus attempt, etc.)
    # since tests aren't necessarily taken same-day.
    pivot = {}
    for test_type, group in df.groupby("test_type"):
        pivot[test_type] = group.sort_values("created_at")["score"].reset_index(drop=True)

    test_types = list(pivot.keys())
    for i in range(len(test_types)):
        for j in range(i + 1, len(test_types)):
            a, b = test_types[i], test_types[j]
            n = min(len(pivot[a]), len(pivot[b]))
            if n < 3:
                continue
            corr = pivot[a][:n].corr(pivot[b][:n])
            if pd.isna(corr):
                continue
            result["correlations"].append({
                "test_a": a,
                "test_b": b,
                "correlation": round(float(corr), 2),
                "n_pairs": n,
            })

    # --- Population-level logistic regression: predict low mood from --
    # focus + memory scores, once there's enough data across all users.
    all_df = pd.DataFrame([dict(r) for r in all_rows])
    wide = all_df.pivot_table(
        index="user_id", columns="test_type", values="score", aggfunc="mean"
    )

    MIN_ROWS = 20
    if {"mood", "focus", "memory"}.issubset(wide.columns) and wide.dropna(
        subset=["mood", "focus", "memory"]
    ).shape[0] >= MIN_ROWS:
        from sklearn.linear_model import LogisticRegression

        sub = wide.dropna(subset=["mood", "focus", "memory"]).copy()
        sub["low_mood"] = (sub["mood"] < sub["mood"].median()).astype(int)

        X = sub[["focus", "memory"]].values
        y = sub["low_mood"].values

        model = LogisticRegression()
        model.fit(X, y)

        if user_id in wide.index and pd.notna(wide.loc[user_id, ["focus", "memory"]]).all():
            user_focus = wide.loc[user_id, "focus"]
            user_memory = wide.loc[user_id, "memory"]
            proba = model.predict_proba([[user_focus, user_memory]])[0][1]
            result["risk_model"] = {
                "trained_on_users": int(sub.shape[0]),
                "low_mood_risk_probability": round(float(proba), 2),
                "note": (
                    "Estimated from a logistic regression trained across all "
                    "MindPulse users, using focus and memory scores to predict "
                    "the chance of a below-median mood score."
                ),
            }
    else:
        result["risk_model"] = {
            "note": (
                f"Not enough data yet to train the risk model "
                f"(need at least {MIN_ROWS} users with mood, focus, and memory "
                "results; currently "
                f"{wide.dropna(subset=['mood', 'focus', 'memory']).shape[0] if {'mood','focus','memory'}.issubset(wide.columns) else 0})."
            )
        }

    return jsonify(result)


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
