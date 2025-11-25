#!/bin/bash

# Full path to main.py
SCRIPT_DIR=$(dirname "$(realpath "$0")")
SCRIPT_PATH="$SCRIPT_DIR/main.py"

# Check if main.py exists
if [ ! -f "$SCRIPT_PATH" ]; then
    echo "Error: main.py not found in the same folder as add_to_startup.sh"
    read -p "Press Enter to exit..."
    exit 1
fi

# Path to python3 (use which to find it)
PYTHON_PATH=$(which python3)
if [ -z "$PYTHON_PATH" ]; then
    echo "Error: python3 not found in PATH. Ensure Python is installed and added to PATH."
    read -p "Press Enter to exit..."
    exit 1
fi

# Service name and path
SERVICE_NAME="internetmonitoring.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"

# Log file (optional, for debugging)
LOG_FILE="$SCRIPT_DIR/startup_log.txt"

# Create the systemd service file
sudo bash -c "cat > \"$SERVICE_PATH\" <<EOF
[Unit]
Description=Internet Monitoring Script

[Service]
ExecStart=$PYTHON_PATH $SCRIPT_PATH > \"$LOG_FILE\" 2>&1
WorkingDirectory=$SCRIPT_DIR
Restart=always
User=$(whoami)

[Install]
WantedBy=multi-user.target
EOF"

# Reload systemd, enable, and start the service
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"

# Check if service was created and started
if sudo systemctl status "$SERVICE_NAME" > /dev/null 2>&1; then
    echo "Service added to startup: $SERVICE_NAME"
    echo "To check: Run 'systemctl status $SERVICE_NAME' or check Task Manager equivalent (htop or systemd tools)."
else
    echo "Error: Failed to create or start service."
    read -p "Press Enter to exit..."
    exit 1
fi

read -p "Press Enter to continue..."