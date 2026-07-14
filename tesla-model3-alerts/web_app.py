#!/usr/bin/env python3
"""
Tesla Model 3 Tracker — Web Dashboard

Run:
    python web_app.py
    open http://localhost:8888
"""

import re
import subprocess
import sys
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, url_for

import database

SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR / "tesla_tracker.db"
LOG_PATH = SCRIPT_DIR / "browse.log"

app = Flask(__name__)
app.secret_key = "tesla-tracker-2026"

def is_scan_running() -> bool:
    result = subprocess.run(["pgrep", "-f", "browse_tesla.py"], capture_output=True)
    return result.returncode == 0


def get_conn():
    return database.init_db(DB_PATH)


def parse_log_sessions(log_path: Path) -> list[dict]:
    """Split browse.log into individual run sessions, most recent first."""
    if not log_path.exists():
        return []

    sessions = []
    current_lines = []

    with open(log_path) as f:
        for line in f:
            line = line.rstrip()
            if "Criteria:" in line and current_lines:
                sessions.append(current_lines)
                current_lines = [line]
            else:
                current_lines.append(line)

    if current_lines:
        sessions.append(current_lines)

    parsed = []
    for lines in reversed(sessions):
        full = "\n".join(lines)

        # Start timestamp from first log line
        ts_match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", lines[0]) if lines else None
        start_time = ts_match.group(1) if ts_match else "—"

        # End timestamp from last timestamped line
        end_time = "—"
        for l in reversed(lines):
            m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", l)
            if m:
                end_time = m.group(1)
                break

        # Status
        if "Access Denied" in full:
            status = "blocked"
        elif "[ERROR]" in full:
            status = "error"
        elif "Stored" in full:
            status = "success"
        else:
            status = "unknown"

        # Vehicles stored
        stored_m = re.search(r"Stored (\d+) vehicles", full)
        vehicles_stored = int(stored_m.group(1)) if stored_m else 0

        # Price range
        price_m = re.search(r"Price range: \$([0-9,]+) – \$([0-9,]+)", full)
        price_range = f"${price_m.group(1)} – ${price_m.group(2)}" if price_m else "—"

        # Matches found
        match_m = re.search(r"(\d+) matching vehicles found", full)
        matches = int(match_m.group(1)) if match_m else 0

        parsed.append({
            "start_time": start_time,
            "end_time": end_time,
            "status": status,
            "vehicles_stored": vehicles_stored,
            "price_range": price_range,
            "matches": matches,
            "lines": lines,
        })

    return parsed


@app.route("/scan-status")
def scan_status():
    return {"running": is_scan_running()}


@app.route("/run-scan", methods=["POST"])
def run_scan():
    if is_scan_running():
        flash("A scan is already in progress.", "warning")
        return redirect(url_for("index"))
    with open(LOG_PATH, "a") as log_file:
        subprocess.Popen(
            [sys.executable, str(SCRIPT_DIR / "browse_tesla.py"), "--no-delay"],
            stdout=log_file,
            stderr=log_file,
            cwd=str(SCRIPT_DIR),
        )
    flash("Scan started — check Run Logs for progress.", "success")
    return redirect(url_for("index"))



@app.route("/")
def index():
    conn = get_conn()
    summary = database.get_daily_summary(conn)
    stats = database.get_market_stats(conn)
    conn.close()
    sessions = parse_log_sessions(LOG_PATH)
    recent = sessions[:5]  # last 5 runs for dashboard
    return render_template("index.html", summary=summary, stats=stats, recent=recent)


@app.route("/listings")
def listings():
    conn = get_conn()
    vehicles = database.get_all_vehicles(conn)
    conn.close()
    return render_template("listings.html", vehicles=vehicles)


@app.route("/sold")
def sold():
    conn = get_conn()
    vehicles = database.get_sold_vehicles(conn)
    conn.close()
    return render_template("sold.html", vehicles=vehicles)


@app.route("/vehicle/<vin>")
def vehicle(vin):
    conn = get_conn()
    v = database.get_vehicle(conn, vin)
    history = database.get_price_history(conn, vin)
    conn.close()
    if not v:
        abort(404)
    return render_template("vehicle.html", vehicle=v, history=history)


@app.route("/logs")
def logs():
    sessions = parse_log_sessions(LOG_PATH)
    return render_template("logs.html", sessions=sessions)


if __name__ == "__main__":
    import sys
    # Disable reloader when running as a systemd service so the PID stays stable;
    # keep debug=True so tracebacks appear in the browser during development.
    interactive = sys.stdout.isatty()
    app.run(host="0.0.0.0", port=8888, debug=True, use_reloader=interactive)
