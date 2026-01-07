#!/bin/bash
set -e

# --- Configuration ---
REPO_BASE="https://raw.githubusercontent.com/cpressland/rpi-cd-ripper/refs/heads/main/src"
COPYPARTY_SCRIPT_URL="https://raw.githubusercontent.com/9001/copyparty/refs/heads/hovudstraum/bin/u2c.py"
ENV_FILE="/etc/rip-audio-cd.env"

# --- Colors ---
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# --- Check Root ---
if [ "$EUID" -ne 0 ]; then
  log_error "Please run as root (e.g., sudo bash install.sh)"
  exit 1
fi

# --- 1. Install System Dependencies ---
log_info "Updating apt and installing dependencies..."
apt-get update -qq
apt-get install -y -qq neovim wget lame flac abcde cdparanoia python3 python3-requests

# --- 2. Create Directories ---
log_info "Creating directories..."
mkdir -p /srv/ripped-music

# --- 3. Download Scripts & Configs ---
log_info "Downloading configuration files..."

# Copyparty Upload Script
wget -q "$COPYPARTY_SCRIPT_URL" -O /usr/local/bin/u2c.py
chmod +x /usr/local/bin/u2c.py
log_success "Installed u2c.py"

# Udev Rule
wget -q "$REPO_BASE/99-cd-audio-processing.rules" -O /etc/udev/rules.d/99-cd-audio-processing.rules
log_success "Installed Udev rules"

# abcde Config
wget -q "$REPO_BASE/abcde.conf" -O /etc/abcde.conf
log_success "Installed abcde.conf"

# Systemd Services
wget -q "$REPO_BASE/copyparty-upload.service" -O /etc/systemd/system/copyparty-upload.service
wget -q "$REPO_BASE/rip-audio-cd%40.service" -O /etc/systemd/system/rip-audio-cd@.service
log_success "Installed Systemd units"

# Main Python Script
wget -q "$REPO_BASE/rip-audio-cd.py" -O /usr/local/bin/rip-audio-cd.py
chmod +x /usr/local/bin/rip-audio-cd.py
log_success "Installed rip-audio-cd.py"

# --- 5. Configure Environment File ---
if [ -f "$ENV_FILE" ]; then
    log_info "Environment file $ENV_FILE already exists. Skipping..."
else
    log_info "Creating default environment file at $ENV_FILE..."
    cat <<EOF > "$ENV_FILE"
# Configuration for CD Ripper
# URL to your Copyparty upload directory
COPYPARTY_URL="https://files.example.com/uploads/"

# Password for Copyparty upload
COPYPARTY_PASSWORD="change_me"

# Telegram Bot Token
TELEGRAM_TOKEN=""

# Telegram Chat ID
CHAT_ID=""
EOF
    log_success "Created $ENV_FILE"
fi

# --- 6. Reload System ---
log_info "Reloading system daemons..."
systemctl daemon-reload
udevadm control --reload
log_success "System reloaded."

# --- 7. Final Message ---
echo ""
echo -e "${GREEN}Installation Complete!${NC}"
echo "------------------------------------------------"
echo "Next Steps:"
echo -e "1. Edit the configuration file with your secrets:"
echo -e "   ${BLUE}sudo nvim $ENV_FILE${NC}"
echo ""
echo "2. Insert a CD to test the system."
echo "   View logs with: tail -f /var/log/cdrip.log"
echo "------------------------------------------------"
