import sqlite3
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = "calorie_tracker.db"
UPLOADS_DIR = Path("uploads")


def get_connection():
    """Get SQLite connection with row factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS utensils (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            type        TEXT NOT NULL,
            diameter_cm REAL,
            depth_cm    REAL,
            volume_ml   REAL,
            notes       TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meal_logs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            image_path    TEXT,
            utensil_id    INTEGER REFERENCES utensils(id),
            fill_level    REAL,
            dish_name     TEXT,
            weight_g      REAL,
            total_kcal    REAL,
            ingredients   TEXT,
            logged_at     TEXT DEFAULT (datetime('now'))
        )
    """)

    # Enable auto-vacuum to clean up deleted records
    cursor.execute("PRAGMA auto_vacuum = FULL")
    cursor.execute("PRAGMA journal_mode = WAL")  # Write-ahead logging for better concurrency

    conn.commit()
    conn.close()
    logger.info("Database initialized")
    
    # Clean old uploaded images
    cleanup_old_uploads()


def cleanup_old_uploads(days_old=7):
    """Delete uploaded images older than N days to save disk space."""
    try:
        cutoff_time = datetime.now() - timedelta(days=days_old)
        cutoff_timestamp = cutoff_time.timestamp()
        
        deleted_count = 0
        for image_file in UPLOADS_DIR.glob("*.jpg"):
            if image_file.stat().st_mtime < cutoff_timestamp:
                image_file.unlink()
                deleted_count += 1
        
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old images")
    except Exception as e:
        logger.warning(f"Cleanup failed: {str(e)}")


# ── Utensil CRUD ──────────────────────────────────────────────────────────────

def create_utensil(name, utensil_type, diameter_cm=None, depth_cm=None,
                   volume_ml=None, notes=None):
    """Create a new utensil profile."""
    
    if volume_ml is None and diameter_cm and depth_cm:
        import math
        r = diameter_cm / 2
        volume_ml = round(math.pi * r * r * depth_cm * 0.85, 1)

    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO utensils (name, type, diameter_cm, depth_cm, volume_ml, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, utensil_type, diameter_cm, depth_cm, volume_ml, notes))
        conn.commit()
        
        utensil = conn.execute(
            "SELECT * FROM utensils WHERE name = ?", (name,)
        ).fetchone()
        
        logger.info(f"Created utensil: {name}")
        return dict(utensil)
    except sqlite3.IntegrityError:
        raise ValueError(f"Utensil '{name}' already exists.")
    finally:
        conn.close()


def get_all_utensils():
    """Get all utensil profiles."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM utensils ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_utensil(utensil_id):
    """Get a specific utensil by ID."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM utensils WHERE id = ?", (utensil_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_utensil(utensil_id, **fields):
    """Update a utensil profile."""
    allowed = {"name", "type", "diameter_cm", "depth_cm", "volume_ml", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    
    if not updates:
        raise ValueError("No valid fields to update.")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [utensil_id]

    conn = get_connection()
    conn.execute(
        f"UPDATE utensils SET {set_clause} WHERE id = ?", values
    )
    conn.commit()
    conn.close()
    logger.info(f"Updated utensil {utensil_id}")


def delete_utensil(utensil_id):
    """Delete a utensil profile."""
    conn = get_connection()
    conn.execute("DELETE FROM utensils WHERE id = ?", (utensil_id,))
    conn.commit()
    conn.close()
    logger.info(f"Deleted utensil {utensil_id}")


# ── Meal log CRUD ─────────────────────────────────────────────────────────────

def log_meal(image_path, utensil_id, fill_level, dish_name,
             weight_g, total_kcal, ingredients, raw_response=""):
    """Log a meal analysis. raw_response param kept for backwards compatibility but not stored."""
    
    conn = get_connection()
    cursor = conn.execute("""
        INSERT INTO meal_logs
            (image_path, utensil_id, fill_level, dish_name, weight_g, total_kcal, ingredients)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        image_path, utensil_id, fill_level, dish_name,
        weight_g, total_kcal,
        json.dumps(ingredients, ensure_ascii=False)
    ))
    conn.commit()
    meal_id = cursor.lastrowid
    conn.close()
    
    logger.info(f"Logged meal {meal_id}: {dish_name}, {total_kcal} kcal")
    return meal_id


def get_meal_history(limit=20):
    """Get recent meal logs."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT ml.*, u.name AS utensil_name, u.type AS utensil_type
        FROM meal_logs ml
        LEFT JOIN utensils u ON ml.utensil_id = u.id
        ORDER BY ml.logged_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    results = []
    for r in rows:
        row = dict(r)
        row["ingredients"] = json.loads(row["ingredients"] or "[]")
        results.append(row)
    
    return results


def get_daily_summary(date_str=None):
    """Get daily calorie total."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    conn = get_connection()
    row = conn.execute("""
        SELECT
            COUNT(*) AS meals,
            ROUND(SUM(total_kcal), 1) AS total_kcal
        FROM meal_logs
        WHERE DATE(logged_at) = ?
    """, (date_str,)).fetchone()
    conn.close()
    
    result = {"date": date_str, **dict(row)}
    logger.info(f"Daily summary for {date_str}: {result['meals']} meals, {result['total_kcal']} kcal")
    return result