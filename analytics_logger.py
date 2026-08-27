import json
import os
import time
from threading import Lock

ANALYTICS_FILE = "game_analytics.jsonl"
file_lock = Lock()

def generate_session_id(ip_address):
    """Generates a unique session ID using IP address + Monotonic timestamp nanoseconds."""
    mono_ns = time.monotonic_ns()
    clean_ip = ip_address.replace(":", "_") if ip_address else "127.0.0.1"
    return f"{clean_ip}_{mono_ns}"

def log_game_session(session_data):
    """Appends a single JSON string line thread-safely to the local filesystem."""
    try:
        json_line = json.dumps(session_data)
        with file_lock:
            with open(ANALYTICS_FILE, "a", encoding="utf-8") as f:
                f.write(json_line + "\n")
        print(f"[Analytics] Successfully logged game session: {session_data['session_id']}")
    except Exception as e:
        print(f"[Analytics Error] Failed to write log: {e}")