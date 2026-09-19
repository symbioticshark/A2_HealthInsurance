"""Shared terminal flow for free API validation and key replacement."""
import os

from backend import api_preflight, live_backend
from config import local_settings
from run.cli_input import masked_input


def _choice(prompt, valid):
    valid = {str(item).upper() for item in valid}
    while True:
        answer = input(prompt).strip().upper()
        if answer in valid:
            return answer
        print(f"Please choose one of: {', '.join(sorted(valid))}")


def configure_api_key(force=False):
    if live_backend.get_api_key() and not force:
        return True
    while True:
        key = masked_input("OpenRouter API key (masked with *, B to go back): ").strip()
        if key.upper() == "B":
            return False
        if not key:
            print("API key cannot be empty.")
            continue
        local_settings.save_local_config({"OPENROUTER_API_KEY": key})
        live_backend.set_runtime_api_key(key)
        environment_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if environment_key and environment_key != key:
            print(
                "Note: a different OPENROUTER_API_KEY environment variable is set. "
                "The environment variable has priority and remains active. The entered key "
                "was saved as the fallback used after that variable is updated or removed."
            )
        return True


def print_api_check(result):
    print(f"API key source: {result.key_source}")
    print(f"API connection: {'ready' if result.ok else 'not ready'} - {result.message}")


def check_api_interactive(allow_replace=True):
    while True:
        print("Checking OpenRouter API connection (no model request)...")
        result = api_preflight.check_api_connection()
        print_api_check(result)
        if result.ok:
            return True
        choices = {"1", "B"}
        print("  1. Retry")
        if allow_replace:
            print("  2. Enter or replace API key")
            choices.add("2")
        print("  B. Back")
        selected = _choice("Select: ", choices)
        if selected == "B":
            return False
        if selected == "2" and not configure_api_key(force=True):
            return False


def ensure_api_ready():
    if not live_backend.get_api_key() and not configure_api_key():
        return False
    return check_api_interactive(allow_replace=True)
