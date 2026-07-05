import sqlite3

PRESET_SETTINGS: list[tuple[str, str]] = [
    ("autosave_interval", "60"),
    ("request_log_max", "10000"),
    ("mock_path_prefix", ""),
]


def _seed_settings(conn: sqlite3.Connection) -> None:
    for key, value in PRESET_SETTINGS:
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )


def run_seed(conn: sqlite3.Connection) -> None:
    _seed_settings(conn)
