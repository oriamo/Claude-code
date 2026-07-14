import datetime
import json
import sqlite3
from pathlib import Path


def init_db(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS vehicles (
            vin             TEXT PRIMARY KEY,
            year            INTEGER,
            trim            TEXT,
            color           TEXT,
            interior        TEXT,
            city            TEXT,
            state           TEXT,
            location_str    TEXT,
            url             TEXT,
            is_repaired     BOOLEAN DEFAULT 0,
            title_status    TEXT DEFAULT '',
            options_raw     TEXT DEFAULT '[]',
            supercharging   TEXT DEFAULT '',
            fsd             TEXT DEFAULT '',
            autopilot       TEXT DEFAULT '',
            wheel_type      TEXT DEFAULT '',
            first_seen_date TEXT,
            last_seen_date  TEXT,
            created_at      TEXT DEFAULT (date('now'))
        );

        CREATE TABLE IF NOT EXISTS price_history (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            vin           TEXT NOT NULL REFERENCES vehicles(vin),
            scan_date     TEXT NOT NULL,
            scan_time     TEXT NOT NULL DEFAULT '00:00:00',
            price         INTEGER,
            mileage       INTEGER,
            shipping_cost INTEGER,
            total_cost    INTEGER,
            score         REAL,
            UNIQUE(vin, scan_date, scan_time)
        );

        CREATE TABLE IF NOT EXISTS daily_summary (
            scan_date          TEXT PRIMARY KEY,
            total_listings     INTEGER,
            min_price          INTEGER,
            max_price          INTEGER,
            avg_price          REAL,
            min_mileage        INTEGER,
            max_mileage        INTEGER,
            avg_mileage        REAL,
            listings_under_22k INTEGER
        );
    """)

    # Migrate: if price_history is missing scan_time, recreate with updated schema.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(price_history)")}
    if "scan_time" not in cols:
        conn.executescript("""
            CREATE TABLE price_history_new (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                vin           TEXT NOT NULL REFERENCES vehicles(vin),
                scan_date     TEXT NOT NULL,
                scan_time     TEXT NOT NULL DEFAULT '00:00:00',
                price         INTEGER,
                mileage       INTEGER,
                shipping_cost INTEGER,
                total_cost    INTEGER,
                score         REAL,
                UNIQUE(vin, scan_date, scan_time)
            );
            INSERT INTO price_history_new
                SELECT id, vin, scan_date, '09:00:00', price, mileage,
                       shipping_cost, total_cost, score
                FROM price_history;
            DROP TABLE price_history;
            ALTER TABLE price_history_new RENAME TO price_history;
        """)

    conn.commit()
    return conn


def upsert_vehicle(conn: sqlite3.Connection, v: dict, scan_date: str):
    """v is a parsed vehicle dict (output of parse_vehicle())."""
    raw = v.get("raw_data", {})
    options_raw = json.dumps(raw.get("OPTIONS_RAW", []))
    conn.execute("""
        INSERT INTO vehicles (
            vin, year, trim, color, interior, city, state, location_str, url,
            is_repaired, title_status, options_raw, supercharging, fsd,
            autopilot, wheel_type, first_seen_date, last_seen_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(vin) DO UPDATE SET
            last_seen_date = excluded.last_seen_date,
            is_repaired    = excluded.is_repaired,
            title_status   = CASE WHEN excluded.title_status != ''
                                  THEN excluded.title_status
                                  ELSE title_status END
    """, (
        v["vin"], v["year"], v["trim"], v["color"], v["interior"],
        v["city"], v["state"], v["location_str"], v["url"],
        int(v["is_repaired"]), v["title_status"],
        options_raw,
        raw.get("SUPERCHARGING", ""),
        raw.get("FSD", ""),
        raw.get("AUTOPILOT", ""),
        raw.get("WHEEL_TYPE", ""),
        scan_date, scan_date,
    ))


def insert_price_snapshot(conn: sqlite3.Connection, vin: str, scan_date: str, v: dict):
    """Insert a snapshot only if price or mileage changed since the last recorded snapshot.
    Allows multiple snapshots per day so intra-day changes are captured."""
    last = conn.execute(
        "SELECT price, mileage FROM price_history WHERE vin = ? ORDER BY scan_date DESC, scan_time DESC LIMIT 1",
        (vin,),
    ).fetchone()

    if last and last["price"] == v.get("price") and last["mileage"] == v.get("mileage"):
        return  # nothing changed — skip

    scan_time = datetime.datetime.now().strftime("%H:%M:%S")
    conn.execute("""
        INSERT OR IGNORE INTO price_history (vin, scan_date, scan_time, price, mileage)
        VALUES (?, ?, ?, ?, ?)
    """, (vin, scan_date, scan_time, v.get("price"), v.get("mileage")))


def update_price_snapshot_enriched(conn: sqlite3.Connection, vin: str, scan_date: str, v: dict):
    """Fill in shipping/total/score on the most-recent price_history row after enrichment."""
    conn.execute("""
        UPDATE price_history
        SET shipping_cost = ?, total_cost = ?, score = ?
        WHERE id = (
            SELECT id FROM price_history
            WHERE vin = ? AND scan_date = ?
            ORDER BY scan_time DESC LIMIT 1
        )
    """, (v.get("shipping_cost"), v.get("total_cost"), v.get("score"), vin, scan_date))


def insert_daily_summary(conn: sqlite3.Connection, scan_date: str, raw_vehicles: list):
    """Upsert market stats for the day — later same-day scans update the numbers."""
    prices = [v.get("Price", 0) or v.get("price", 0) for v in raw_vehicles]
    prices = [p for p in prices if p > 0]
    mileages = [v.get("Odometer", 0) or v.get("mileage", 0) for v in raw_vehicles]
    mileages = [m for m in mileages if m > 0]
    conn.execute("""
        INSERT INTO daily_summary (
            scan_date, total_listings, min_price, max_price, avg_price,
            min_mileage, max_mileage, avg_mileage, listings_under_22k
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(scan_date) DO UPDATE SET
            total_listings     = excluded.total_listings,
            min_price          = excluded.min_price,
            max_price          = excluded.max_price,
            avg_price          = excluded.avg_price,
            min_mileage        = excluded.min_mileage,
            max_mileage        = excluded.max_mileage,
            avg_mileage        = excluded.avg_mileage,
            listings_under_22k = excluded.listings_under_22k
    """, (
        scan_date,
        len(raw_vehicles),
        min(prices) if prices else None,
        max(prices) if prices else None,
        round(sum(prices) / len(prices), 2) if prices else None,
        min(mileages) if mileages else None,
        max(mileages) if mileages else None,
        round(sum(mileages) / len(mileages), 2) if mileages else None,
        sum(1 for p in prices if p <= 22000),
    ))


# ── Read helpers ──────────────────────────────────────────────────────────────

def get_all_vehicles(conn: sqlite3.Connection) -> list[dict]:
    """Active listings only — vehicles seen within the last 2 days."""
    cur = conn.execute("""
        SELECT v.*,
               ph1.price         AS latest_price,
               ph1.mileage       AS latest_mileage,
               ph1.shipping_cost AS latest_shipping,
               ph1.total_cost    AS latest_total,
               ph1.score         AS latest_score,
               ph1.scan_date     AS price_date,
               ph2.price         AS prev_price
        FROM vehicles v
        LEFT JOIN price_history ph1 ON ph1.id = (
            SELECT id FROM price_history WHERE vin = v.vin
            ORDER BY scan_date DESC, scan_time DESC LIMIT 1
        )
        LEFT JOIN price_history ph2 ON ph2.id = (
            SELECT id FROM price_history WHERE vin = v.vin
            ORDER BY scan_date DESC, scan_time DESC LIMIT 1 OFFSET 1
        )
        WHERE julianday('now') - julianday(v.last_seen_date) < 2
        ORDER BY v.last_seen_date DESC, ph1.price ASC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        r["options_list"] = json.loads(r.get("options_raw") or "[]")
        prev = r.get("prev_price")
        latest = r.get("latest_price")
        r["price_drop"] = (prev - latest) if prev and latest and latest < prev else None
    return rows


def get_sold_vehicles(conn: sqlite3.Connection) -> list[dict]:
    """Vehicles not seen for 2+ days, ordered by most recently gone."""
    cur = conn.execute("""
        SELECT v.*,
               ph1.price     AS latest_price,
               ph1.mileage   AS latest_mileage,
               ph1.scan_date AS price_date,
               CAST(julianday('now') - julianday(v.last_seen_date) AS INTEGER) AS days_gone
        FROM vehicles v
        LEFT JOIN price_history ph1 ON ph1.id = (
            SELECT id FROM price_history WHERE vin = v.vin
            ORDER BY scan_date DESC, scan_time DESC LIMIT 1
        )
        WHERE julianday('now') - julianday(v.last_seen_date) >= 2
        ORDER BY v.last_seen_date DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        r["options_list"] = json.loads(r.get("options_raw") or "[]")
    return rows


def get_vehicle(conn: sqlite3.Connection, vin: str) -> dict | None:
    cur = conn.execute("SELECT * FROM vehicles WHERE vin = ?", (vin,))
    row = cur.fetchone()
    if not row:
        return None
    v = dict(row)
    v["options_list"] = json.loads(v.get("options_raw") or "[]")
    return v


def get_price_history(conn: sqlite3.Connection, vin: str) -> list[dict]:
    cur = conn.execute("""
        SELECT scan_date, scan_time, price, mileage, shipping_cost, total_cost, score
        FROM price_history WHERE vin = ?
        ORDER BY scan_date ASC, scan_time ASC
    """, (vin,))
    return [dict(r) for r in cur.fetchall()]


def get_daily_summary(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.execute("""
        SELECT scan_date, total_listings, min_price, avg_price, max_price,
               listings_under_22k, avg_mileage
        FROM daily_summary ORDER BY scan_date ASC
    """)
    return [dict(r) for r in cur.fetchall()]


def get_market_stats(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]

    row = conn.execute("""
        SELECT ph.price, ph.scan_date, v.vin, v.year, v.trim
        FROM price_history ph
        JOIN vehicles v ON v.vin = ph.vin
        WHERE ph.price > 0
        ORDER BY ph.price ASC LIMIT 1
    """).fetchone()
    cheapest = dict(row) if row else {}

    days = conn.execute(
        "SELECT COUNT(DISTINCT scan_date) FROM daily_summary"
    ).fetchone()[0]

    latest = conn.execute(
        "SELECT scan_date, total_listings FROM daily_summary ORDER BY scan_date DESC LIMIT 1"
    ).fetchone()
    latest = dict(latest) if latest else {}

    return {
        "total_vins": total,
        "cheapest_ever": cheapest.get("price"),
        "cheapest_vin": cheapest.get("vin"),
        "cheapest_date": cheapest.get("scan_date"),
        "cheapest_label": f"{cheapest.get('year', '')} {cheapest.get('trim', '')}".strip(),
        "days_tracking": days,
        "latest_scan_date": latest.get("scan_date"),
        "latest_total_listings": latest.get("total_listings"),
    }
