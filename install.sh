#!/usr/bin/env bash
# ==============================================================================
# Installer script for pylontech-mqtt on Raspberry Pi 3 B+
# ==============================================================================

set -euo pipefail

INSTALL_DIR="/opt/pylontech-mqtt"
CONFIG_DIR="/etc/pylontech-mqtt"
SERVICE_FILE="/etc/systemd/system/pylontech-mqtt.service"
CURRENT_USER="${SUDO_USER:-$USER}"

echo "======================================================================"
echo "  Installing Pylontech US2000 to Home Assistant MQTT Gateway"
echo "======================================================================"

# Check for root / sudo
if [ "$EUID" -ne 0 ]; then
  echo "[-] Please run this installer with sudo: sudo ./install.sh"
  exit 1
fi

echo "[+] Updating apt repositories and installing prerequisites..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git

# Add user to dialout group for serial port access
echo "[+] Ensuring user '${CURRENT_USER}' is in the 'dialout' group..."
usermod -a -G dialout "${CURRENT_USER}" || true

# Create directories
echo "[+] Creating installation directories..."
mkdir -p "${INSTALL_DIR}"
mkdir -p "${CONFIG_DIR}"

# Copy source files
echo "[+] Copying application files to ${INSTALL_DIR}..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -r "${SCRIPT_DIR}/pylontech_mqtt" "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/requirements.txt" "${INSTALL_DIR}/"

# Setup Python virtual environment
echo "[+] Creating Python virtual environment in ${INSTALL_DIR}/venv..."
python3 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip -q
"${INSTALL_DIR}/venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt" -q

# Set permissions
chown -R "${CURRENT_USER}:${CURRENT_USER}" "${INSTALL_DIR}"

# Create default configuration if not present
if [ ! -f "${CONFIG_DIR}/config.yaml" ]; then
  echo "[+] Creating template configuration at ${CONFIG_DIR}/config.yaml..."
  cp "${SCRIPT_DIR}/config.yaml.example" "${CONFIG_DIR}/config.yaml"
  chown "${CURRENT_USER}:${CURRENT_USER}" "${CONFIG_DIR}/config.yaml"
  chmod 600 "${CONFIG_DIR}/config.yaml"
else
  echo "[*] Existing configuration at ${CONFIG_DIR}/config.yaml preserved."
fi

# Install systemd service
echo "[+] Installing systemd service file..."
# Adjust user in service file to current user if not 'pi'
sed "s/User=pi/User=${CURRENT_USER}/g; s/Group=pi/Group=${CURRENT_USER}/g" \
  "${SCRIPT_DIR}/systemd/pylontech-mqtt.service" > "${SERVICE_FILE}"

systemctl daemon-reload
systemctl enable pylontech-mqtt.service

echo ""
echo "======================================================================"
echo "  Installation Completed Successfully!"
echo "======================================================================"
echo ""
echo "Next Steps:"
echo "1. Edit your configuration file with your Home Assistant MQTT broker IP:"
echo "   sudo nano ${CONFIG_DIR}/config.yaml"
echo "   (Note: For built-in GPIO UART, set port: \"/dev/serial0\")"
echo ""
echo "2. Test the connection and battery readings once:"
echo "   ${INSTALL_DIR}/venv/bin/python3 -m pylontech_mqtt.main --config ${CONFIG_DIR}/config.yaml --test"
echo ""
echo "3. Start and check the background service:"
echo "   sudo systemctl start pylontech-mqtt"
echo "   sudo systemctl status pylontech-mqtt"
echo ""
echo "4. Follow live service logs:"
echo "   sudo journalctl -u pylontech-mqtt -f"
echo "======================================================================"
