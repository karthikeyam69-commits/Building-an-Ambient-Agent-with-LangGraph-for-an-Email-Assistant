import os
import io
import re
import pandas as pd
from flask import Flask, request, render_template, redirect, url_for, session

app = Flask(__name__)
app.secret_key = os.urandom(24)


# ── Lenient Email Parsing ──────────────────────────────────────────────────────

def parse_email(raw_text):
    """Best-effort header extraction — all fields optional."""
    def extract(pattern):
        m = re.search(pattern, raw_text, re.IGNORECASE | re.MULTILINE)
        return m.group(1).strip() if m else ""

    return {
        "Message-ID": extract(r"^Message-ID:\s*(.+)$"),
        "From":       extract(r"^From:\s*(.+)$"),
        "To":         extract(r"^To:\s*(.+)$"),
        "Subject":    extract(r"^Subject:\s*(.+)$"),
    }


def categorize(text):
    """Classify using the entire email text, not just the subject."""
    if not text:
        return "Unknown"
    t = text.lower()
    if any(k in t for k in ["meeting", "schedule", "agenda", "conference", "call", "interview"]):
        return "Work"
    if any(k in t for k in ["invoice", "payment", "billing", "receipt", "transaction", "amount due", "bank"]):
        return "Finance"
    if any(k in t for k in ["party", "invitation", "celebrate", "birthday", "wedding", "gathering", "event"]):
        return "Personal"
    if any(k in t for k in ["unsubscribe", "newsletter", "offer", "deal", "discount", "promo", "sale"]):
        return "Promotions"
    return "Other"


def agent_action(category):
    return {
        "Work":       "Add to calendar / notify team",
        "Finance":    "Forward to accounts department",
        "Personal":   "Mark as personal / no action",
        "Promotions": "Move to Promotions folder",
        "Unknown":    "Flag for review",
    }.get(category, "Archive")


def process_single(raw_text):
    headers = parse_email(raw_text)
    cat = categorize(raw_text)
    return {
        "From":         headers["From"] or "—",
        "To":           headers["To"] or "—",
        "Subject":      headers["Subject"] or "—",
        "Category":     cat,
        "Agent_Action": agent_action(cat),
    }


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/input")
def input_page():
    error = session.pop("input_error", None)
    return render_template("input.html", error=error)


@app.route("/process", methods=["POST"])
def process():
    mode = request.form.get("mode")
    results = []
    error = None

    if mode == "text":
        raw = request.form.get("email_text", "").strip()
        if not raw:
            error = "Please paste an email before submitting."
        else:
            results = [process_single(raw)]

    elif mode == "csv":
        f = request.files.get("csv_file")
        if not f or not f.filename:
            error = "Please select a CSV file."
        elif not f.filename.endswith(".csv"):
            error = "Only .csv files are supported."
        else:
            try:
                df = pd.read_csv(io.StringIO(f.read().decode("utf-8")))
                col = next((c for c in ["message", "text", "body"] if c in df.columns), None)
                if col is None:
                    error = "CSV must have a 'message', 'text', or 'body' column."
                else:
                    for _, row in df.iterrows():
                        r = process_single(str(row[col]))
                        if "file" in df.columns:
                            r["File"] = row["file"]
                        results.append(r)
            except Exception as e:
                error = f"Failed to parse CSV: {e}"
    else:
        error = "Unknown submission mode."

    if error:
        session["input_error"] = error
        return redirect(url_for("input_page"))

    session["results"] = results
    return redirect(url_for("output_page"))


@app.route("/output")
def output_page():
    results = session.get("results")
    if not results:
        return redirect(url_for("input_page"))
    stats = {}
    for r in results:
        stats[r["Category"]] = stats.get(r["Category"], 0) + 1
    return render_template("output.html", results=results, stats=stats)


if __name__ == "__main__":
    app.run(debug=True)
