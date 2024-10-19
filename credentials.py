import os

API_KEY_FILE = "openai_key.txt"

def load_api_key():
    if os.path.exists(API_KEY_FILE):
        with open(API_KEY_FILE, "r") as f:
            return f.read().strip()
    return "<your key>"

OPENAI_API_KEY = load_api_key()