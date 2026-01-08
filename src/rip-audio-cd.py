#!/usr/bin/env -S python3

import sys
import subprocess
import os
import requests
import logging
import re
import fcntl
from pathlib import Path

# --- Configuration ---
LOG_FILE = Path("/var/log/cdrip.log")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
ABCDE_CMD = ["abcde", "-N"]

# --- Constants for CDROM ioctl ---
CDROM_DRIVE_STATUS = 0x5326
CDS_NO_DISC = 1
CDS_TRAY_OPEN = 2
CDS_DRIVE_NOT_READY = 3
CDS_DISC_OK = 4

# Setup Logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def get_drive_status(device_path):
    """
    Checks the physical status of the CD drive using Linux ioctl.
    Returns True if a disc is present and ready (CDS_DISC_OK).
    """
    try:
        # Open device in non-blocking mode just to query status
        fd = os.open(device_path, os.O_RDONLY | os.O_NONBLOCK)
        status = fcntl.ioctl(fd, CDROM_DRIVE_STATUS)
        os.close(fd)

        if status == CDS_DISC_OK:
            return True, "Disc Present"
        elif status == CDS_TRAY_OPEN:
            return False, "Tray Open"
        elif status == CDS_NO_DISC:
            return False, "No Disc"
        elif status == CDS_DRIVE_NOT_READY:
            return False, "Drive Not Ready"
        else:
            return False, f"Unknown Status ({status})"
    except Exception as e:
        logging.error(f"Failed to query drive status: {e}")
        # If we can't query, assume true to let abcde handle the error naturally
        return True, "Check Failed"

def send_telegram(message, image_url=None):
    """Sends a notification to Telegram."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return

    try:
        if image_url:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            payload = {"chat_id": CHAT_ID, "photo": image_url, "caption": message, "parse_mode": "Markdown"}
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}

        logging.info("Sending Telegram Message")
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        logging.error(f"Failed to send Telegram notification: {e}")

def parse_abcde_log(log_output):
    """Extracts Artist, Album, and Cover URL from abcde stdout."""
    info = {"artist": "Unknown Artist", "album": "Unknown Album", "cover_url": None}

    match_metadata = re.search(r"#1 \(.*?\): ---- (.+?) / (.+?) ----", log_output)
    if match_metadata:
        info["artist"] = match_metadata.group(1).strip()
        info["album"] = match_metadata.group(2).strip()

    match_cover = re.search(r"cover URL: (https?://\S+)", log_output)
    if match_cover:
        info["cover_url"] = match_cover.group(1).strip()

    return info

def main():
    # 1. Validation
    if len(sys.argv) < 2:
        logging.error("No device specified. Usage: script.py <device>")
        sys.exit(1)

    device_name = sys.argv[1]
    device_path = f"/dev/{device_name}"

    logging.info(f"--- Triggered for {device_path} ---")

    # 2. Pre-flight Check: Is there a disc?
    disc_present, status_msg = get_drive_status(device_path)
    if not disc_present:
        logging.info(f"Aborting: {status_msg}")
        # Exit cleanly so systemd doesn't mark it as failed.
        # This prevents the 'CD Rip Failed' notification.
        sys.exit(0)

    # 3. Proceed with Rip
    logging.info(f"Disc confirmed ({status_msg}). Starting rip.")
    send_telegram(f"💿 **CD Rip Started**\nDevice: `{device_path}`")

    try:
        result = subprocess.run(ABCDE_CMD, capture_output=True, text=True, check=True)

        logging.info("abcde output:\n" + result.stdout)
        meta = parse_abcde_log(result.stdout)

        msg = (f"✅ **CD Rip Completed**\n"
               f"🎵 **Artist:** {meta['artist']}\n"
               f"💿 **Album:** {meta['album']}\n"
               f"📂 Device: `{device_path}`")

        send_telegram(msg, image_url=meta['cover_url'])
        logging.info("Rip completed successfully.")

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else e.stdout
        logging.error(f"Rip failed with return code {e.returncode}")
        logging.error(f"Output: {error_msg}")

        subprocess.run(["eject", device_path], check=False)

        send_telegram(f"❌ **CD Rip Failed**\nDevice: `{device_path}`\nError Code: `{e.returncode}`\nLog: Check `/var/log/cdrip.log`")
        sys.exit(e.returncode)

if __name__ == "__main__":
    main()
