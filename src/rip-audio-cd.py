#!/usr/bin/env -S python3

import fcntl
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

# --- Configuration ---
LOG_FILE = Path("/var/log/cdrip.log")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
ABCDE_CMD = ["abcde", "-N"]
COPYPARTY_PASSWORD = os.environ.get("COPYPARTY_PASSWORD")
COPYPARTY_URL = os.environ.get("COPYPARTY_URL")
FINAL_MUSIC_DIR = Path("/srv/ripped-music/flac")
TEMP_RIP_DIR_BASE = Path("/srv/ripped-music/ripping")


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
    datefmt="%Y-%m-%d %H:%M:%S",
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
            payload = {
                "chat_id": CHAT_ID,
                "photo": image_url,
                "caption": message,
                "parse_mode": "Markdown",
            }
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
        sys.exit(0)

    # 3. Create a unique temporary directory for this rip
    TEMP_RIP_DIR_BASE.mkdir(exist_ok=True)
    temp_rip_dir = Path(
        TEMP_RIP_DIR_BASE
        / f"{device_name}-{os.getpid()}-{int(time.time())}"
    )
    temp_rip_dir.mkdir()

    # 4. Proceed with Rip
    logging.info(f"Disc confirmed ({status_msg}). Starting rip into {temp_rip_dir}")
    send_telegram(f"💿 **CD Rip Started**\nDevice: `{device_path}`")

    try:
        # Build abcde command with the unique output directory
        abcde_command = ABCDE_CMD + ["-d", device_path, f"OUTPUTDIR={temp_rip_dir}"]
        result = subprocess.run(
            abcde_command, capture_output=True, text=True, check=True
        )

        logging.info("abcde output:\n" + result.stdout)
        meta = parse_abcde_log(result.stdout)

        # 5. Move to final destination
        flac_dir = temp_rip_dir / "flac"
        album_dirs = [p for p in flac_dir.iterdir() if p.is_dir()]
        if not album_dirs:
            raise FileNotFoundError("Could not find ripped album directory in temp folder.")

        album_dir = album_dirs[0]
        FINAL_MUSIC_DIR.mkdir(exist_ok=True)
        final_album_path = FINAL_MUSIC_DIR / album_dir.name

        # Handle potential name collision
        if final_album_path.exists():
            final_album_path = FINAL_MUSIC_DIR / f"{album_dir.name}-{int(time.time())}"

        shutil.move(str(album_dir), str(final_album_path))
        logging.info(f"Moved album to {final_album_path}")

        # 6. Trigger Upload
        if COPYPARTY_URL and COPYPARTY_PASSWORD:
            try:
                escaped_path = subprocess.check_output(
                    ["systemd-escape", "--path", str(final_album_path)], text=True
                ).strip()

                upload_service_name = f"copyparty-upload@{escaped_path}.service"

                logging.info(f"Starting upload service: {upload_service_name}")
                subprocess.run(["systemctl", "start", upload_service_name], check=True)
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logging.error(f"Failed to start upload service: {e}")
                send_telegram(
                    f"⚠️ **Upload Trigger Failed**\nDevice: `{device_path}`\nAlbum: {final_album_path.name}"
                )

        # 7. Success Notification
        msg = (
            f"✅ **CD Rip Completed**\n"
            f"🎵 **Artist:** {meta['artist']}\n"
            f"💿 **Album:** {meta['album']}\n"
            f"📂 Device: `{device_path}`"
        )
        send_telegram(msg, image_url=meta["cover_url"])
        logging.info("Rip completed successfully.")

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else e.stdout
        logging.error(f"Rip failed with return code {e.returncode}")
        logging.error(f"Output: {error_msg}")

        send_telegram(
            f"❌ **CD Rip Failed**\nDevice: `{device_path}`\nError Code: `{e.returncode}`"
        )
        sys.exit(e.returncode)

    finally:
        # 8. Cleanup and Eject
        if temp_rip_dir.exists():
            logging.info(f"Cleaning up temporary directory: {temp_rip_dir}")
            shutil.rmtree(temp_rip_dir)

        # Eject the disc regardless of outcome
        logging.info(f"Ejecting {device_path}")
        subprocess.run(["eject", device_path], check=False)

if __name__ == "__main__":
    main()
