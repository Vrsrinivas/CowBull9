import csv
import os
import random
from better_profanity import profanity
from flask import Flask, jsonify, render_template, request, session
import ulid

# --- 1. SETUP NLTK CORPUS ---
import nltk

try:
    nltk.data.find("corpora/words")
except LookupError:
    nltk.download("words")

from nltk.corpus import words

app = Flask(__name__)
app.secret_key = 'word_power_game_secure_session_key'

# Initialize profanity filter
profanity.load_censor_words()

# --- 2. MASTER BLACKLIST & CSV SETUP ---
# Hardcoded absolute protection list based on your words
BLOCKED_WORDS_SET = {
    "FUCK", "RAPE", "SLUT", "SEXY", "SEX", "BITCH", 
    "BASTARD", "SHIT", "ASS", "DAMN", "CRAP", "HELL", "COCK", "DICKS"
}
CSV_FILENAME = "blockedwords.csv"

def load_blocked_words_from_csv():
    """Loads additional blocked words from local CSV file and merges them into the master set."""
    if os.path.exists(CSV_FILENAME):
        try:
            with open(CSV_FILENAME, mode="r", encoding="utf-8") as f:
                reader = csv.reader(f)
                for row in reader:
                    for field in row:
                        for word in field.split(","):
                            clean_word = word.strip().upper()
                            if clean_word and clean_word != "WORD" and not clean_word.startswith("#"):
                                BLOCKED_WORDS_SET.add(clean_word)
            print(f"SUCCESS: Loaded and merged blocked words from {CSV_FILENAME}. Total blocked: {len(BLOCKED_WORDS_SET)}")
        except Exception as e:
            print(f"Error reading {CSV_FILENAME}: {e}. Using master hardcoded list.")
    else:
        # Create the CSV file automatically if it doesn't exist
        try:
            with open(CSV_FILENAME, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["word"])
                for w in sorted(BLOCKED_WORDS_SET):
                    writer.writerow([w])
            print(f"Created default {CSV_FILENAME}.")
        except Exception as e:
            print(f"Error creating {CSV_FILENAME}: {e}")

# Load and merge CSV data upon startup
load_blocked_words_from_csv()

# Load all valid English words into an uppercase set for O(1) lookup
ENGLISH_WORDS = set(w.upper() for w in words.words() if w.isalpha() and len(w) > 1)

# Pre-compute and cache strict isograms by length
ISOGRAM_DICTIONARY = {}
for length_key in range(3, 9):
    ISOGRAM_DICTIONARY[length_key] = [
        w for w in ENGLISH_WORDS 
        if len(w) == length_key 
        and len(set(w)) == length_key 
        and w not in BLOCKED_WORDS_SET
        and not profanity.contains_profanity(w)
    ]


def get_secret_words_by_length(length):
    if length in ISOGRAM_DICTIONARY:
        return ISOGRAM_DICTIONARY[length]
    
    return [
        w for w in ENGLISH_WORDS
        if len(w) == length
        and len(set(w)) == length
        and w not in BLOCKED_WORDS_SET
        and not profanity.contains_profanity(w)
    ]


# --- 3. SESSION-WISE ANALYTICS STORAGE ---
# Dictionary to store analytics grouped by unique IP + ULID session keys
sessions_analytics = {}

def get_current_session_key():
    """Generates or retrieves a unique ULID combined with the client's IP address."""
    if 'session_ulid' not in session:
        session['session_ulid'] = str(ulid.new())
    client_ip = request.remote_addr or '127.0.0.1'
    return f"{client_ip}_{session['session_ulid']}"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/get-secret-word", methods=["POST"])
def get_secret_word():
    data = request.get_json() or {}
    length = data.get("word_length", 4)

    valid_candidates = get_secret_words_by_length(length)

    if not valid_candidates:
        return (
            jsonify(
                {"error": f"No valid {length}-letter isograms found in NLTK!"}
            ),
            500,
        )

    secret_word = random.choice(valid_candidates)
    return jsonify({"secret_word": secret_word})


@app.route("/api/guess", methods=["POST"])
def process_guess():
    data = request.get_json() or {}
    guess = data.get("guess", "").strip().upper()
    secret_word = data.get("secret_word", "").strip().upper()
    word_length = data.get("word_length", 4)

    # 1. STRICT BLACKLIST & PROFANITY CHECK (Runs first before anything else)
    if guess in BLOCKED_WORDS_SET or profanity.contains_profanity(guess) or profanity.contains_profanity(secret_word):
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Please keep your guesses clean and appropriate!",
                }
            ),
            400,
        )

    # 2. LENGTH VALIDATION
    if len(guess) != word_length:
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"Word must be exactly {word_length} letters long!",
                }
            ),
            400,
        )

    # 3. REPEATED LETTERS VALIDATION (Strict Isogram Rule)
    if len(set(guess)) != len(guess):
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Repeated letters are not allowed! Must be an isogram.",
                }
            ),
            400,
        )

    # 4. NLTK ENGLISH DICTIONARY VALIDATION
    if guess not in ENGLISH_WORDS:
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"'{guess}' is not a valid English word in the dictionary!",
                }
            ),
            400,
        )

    # 5. CALCULATE COWS & BULLS
    bulls = sum(1 for i in range(word_length) if guess[i] == secret_word[i])
    cows = sum(
        1
        for i in range(word_length)
        if guess[i] in secret_word and guess[i] != secret_word[i]
    )

    return jsonify(
        {
            "success": True,
            "guess": guess,
            "bulls": bulls,
            "cows": cows,
            "is_win": (bulls == word_length),
        }
    )


@app.route("/api/analytics", methods=["GET", "POST"])
def analytics():
    session_key = get_current_session_key()
    client_ip = request.remote_addr or '127.0.0.1'
    ulid_val = session.get('session_ulid')

    # Initialize session tracking entry if it doesn't exist yet
    if session_key not in sessions_analytics:
        sessions_analytics[session_key] = {
            "ip_address": client_ip,
            "ulid": ulid_val,
            "total_games": 0,
            "wins": 0,
            "total_attempts": 0,
            "total_time_seconds": 0,
            "games_history": []
        }

    s_data = sessions_analytics[session_key]

    if request.method == "POST":
        data = request.get_json() or {}
        s_data["total_games"] += 1
        is_win = data.get("is_win", False)
        if is_win:
            s_data["wins"] += 1
        
        attempts = data.get("attempts", 0)
        time_taken = data.get("time_taken", 0)
        
        s_data["total_attempts"] += attempts
        s_data["total_time_seconds"] += time_taken
        
        # Log individual game within the session history
        s_data["games_history"].append({
            "attempts": attempts,
            "time_taken": time_taken,
            "is_win": is_win
        })
        
        return jsonify({"status": "success", "session_key": session_key})

    # GET Request: Return session-wise reports for all tracked sessions
    report_list = []
    for key, data in sessions_analytics.items():
        total = data["total_games"]
        win_rate = f"{round((data['wins'] / total) * 100)}%" if total > 0 else "0%"
        avg_time = f"{round(data['total_time_seconds'] / total)}s" if total > 0 else "0s"
        avg_attempts = round(data["total_attempts"] / total, 1) if total > 0 else 0

        report_list.append({
            "session_id": key,
            "ip_address": data["ip_address"],
            "ulid": data["ulid"],
            "total_games": total,
            "wins": data["wins"],
            "win_rate": win_rate,
            "avg_time_seconds": avg_time,
            "avg_attempts": avg_attempts,
            "games_history": data["games_history"]
        })

    return jsonify(report_list)


if __name__ == "__main__":
    app.run(debug=True, port=5000)