#!/usr/bin/env -S python3

import sys
import subprocess
import os
import requests
import logging
import re
from pathlib import Path

# --- Configuration ---
LOG_FILE = Path("/var/log/cdrip.log")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
ABCDE_CMD = ["abcde", "-N"]  # -N prevents user interaction

# Setup Logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def send_telegram(message, image_url=None):
    """Sends a notification to Telegram, optionally with a cover image."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logging.warning("Telegram credentials missing. Skipping notification.")
        return

    try:
        if image_url:
            # Send Photo with Caption
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            payload = {
                "chat_id": CHAT_ID,
                "photo": image_url,
                "caption": message,
                "parse_mode": "Markdown"
            }
            logging.info(f"Sending Telegram Photo: {image_url}")
        else:
            # Send Text Message
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "Markdown"
            }
            logging.info("Sending Telegram Message")

        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()

    except Exception as e:
        logging.error(f"Failed to send Telegram notification: {e}")
        # Fallback: If sending photo fails (e.g. invalid URL), try sending just text
        if image_url:
             logging.info("Retrying Telegram with text only...")
             send_telegram(message, image_url=None)

def parse_abcde_log(log_output):
    """Extracts Artist, Album, and Cover URL from abcde stdout."""
    info = {
        "artist": "Unknown Artist",
        "album": "Unknown Album",
        "cover_url": None
    }

    # Regex to find the selected match (Assuming match #1 is selected by -N)
    # Pattern looks for: #1 (Source): ---- Artist / Album ----
    match_metadata = re.search(r"#1 \(.*?\): ---- (.+?) / (.+?) ----", log_output)
    if match_metadata:
        info["artist"] = match_metadata.group(1).strip()
        info["album"] = match_metadata.group(2).strip()

    # Regex to find cover URL
    # Pattern looks for: cover URL: http://...
    match_cover = re.search(r"cover URL: (https?://\S+)", log_output)
    if match_cover:
        info["cover_url"] = match_cover.group(1).strip()

    return info

def main():
    # 1. Validation
    if len(sys.argv) < 2:
        logging.error("No device specified. Usage: script.py <device>")
        sys.exit(1)

    device_name = sys.argv[1] # e.g., sr0
    device_path = f"/dev/{device_name}"

    logging.info(f"--- Starting Rip for {device_path} ---")
    send_telegram(f"💿 **CD Rip Started**\nDevice: `{device_path}`")

    # 2. Run abcde
    try:
        # We capture stdout/stderr to parse them
        result = subprocess.run(
            ABCDE_CMD,
            capture_output=True,
            text=True,
            check=True
        )

        # Log the full output
        logging.info("abcde output:\n" + result.stdout)

        # 3. Parse Metadata
        meta = parse_abcde_log(result.stdout)

        # 4. Success Notification
        msg = (
            f"✅ **CD Rip Completed**\n"
            f"🎵 **Artist:** {meta['artist']}\n"
            f"💿 **Album:** {meta['album']}\n"
            f"📂 Device: `{device_path}`"
        )

        send_telegram(msg, image_url=meta['cover_url'])
        logging.info("Rip completed successfully.")

    except subprocess.CalledProcessError as e:
        # 5. Error Handling
        error_msg = e.stderr if e.stderr else e.stdout
        logging.error(f"Rip failed with return code {e.returncode}")
        logging.error(f"Output: {error_msg}")

        # Eject on failure
        subprocess.run(["eject", device_path], check=False)

        send_telegram(
            f"❌ **CD Rip Failed**\n"
            f"Device: `{device_path}`\n"
            f"Error Code: `{e.returncode}`\n"
            f"Log: Check `/var/log/cdrip.log`"
        )
        sys.exit(e.returncode)

if __name__ == "__main__":
    main()
