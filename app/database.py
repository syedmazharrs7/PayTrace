import sqlite3
import os
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("PAYTRACE_DB_PATH", "paytrace.db")

def init_db():
    """Initialize the SQLite database with required tables."""
    logger.info(f"Initializing database at {DB_PATH}")
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. merchant_orders
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS merchant_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                razorpay_order_id TEXT UNIQUE NOT NULL,
                amount INTEGER NOT NULL,
                currency TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 2. webhook_events
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS webhook_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE NOT NULL,
                event_type TEXT NOT NULL,
                entity_id TEXT,
                razorpay_order_id TEXT,
                razorpay_payment_id TEXT,
                amount INTEGER,
                currency TEXT,
                payment_status TEXT,
                payload TEXT,
                created_at INTEGER,
                received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Migration: Add new columns if they don't exist
        cursor.execute("PRAGMA table_info(webhook_events)")
        columns = [col['name'] for col in cursor.fetchall()]
        
        # We don't drop 'payload' because SQLite DROP COLUMN requires v3.35.0+ and rewrites the table.
        # Safest lightweight approach is to add new columns and stop writing to payload.
        if 'razorpay_order_id' not in columns:
            cursor.execute("ALTER TABLE webhook_events ADD COLUMN razorpay_order_id TEXT")
        if 'payload' not in columns:
            cursor.execute("ALTER TABLE webhook_events ADD COLUMN payload TEXT")
        if 'razorpay_payment_id' not in columns:
            cursor.execute("ALTER TABLE webhook_events ADD COLUMN razorpay_payment_id TEXT")
        if 'amount' not in columns:
            cursor.execute("ALTER TABLE webhook_events ADD COLUMN amount INTEGER")
        if 'currency' not in columns:
            cursor.execute("ALTER TABLE webhook_events ADD COLUMN currency TEXT")
        if 'payment_status' not in columns:
            cursor.execute("ALTER TABLE webhook_events ADD COLUMN payment_status TEXT")

        
        # 3. incidents
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                razorpay_order_id TEXT,
                razorpay_payment_id TEXT,
                amount INTEGER,
                currency TEXT,
                razorpay_status TEXT,
                merchant_status TEXT,
                incident_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                UNIQUE(event_id, incident_type)
            )
        """)

        # 4. incident_analyses
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS incident_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id INTEGER UNIQUE NOT NULL,
                summary TEXT NOT NULL,
                what_happened TEXT NOT NULL,
                likely_cause TEXT NOT NULL,
                impact TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                action_type TEXT NOT NULL,
                action_safety TEXT NOT NULL,
                confidence TEXT NOT NULL,
                uncertainty TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(incident_id) REFERENCES incidents(id)
            )
        """)

        # 5. audit_trail
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_trail (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                reason TEXT NOT NULL,
                safety_classification TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(incident_id) REFERENCES incidents(id)
            )
        """)
        
        conn.commit()

@contextmanager
def get_db():
    """Provides a transactional scope around a series of operations."""
    conn = sqlite3.connect(DB_PATH)
    # Return rows as dictionary-like objects
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# Initialize the database immediately upon importing if not explicitly disabled
if os.getenv("SKIP_DB_INIT") != "true":
    init_db()
