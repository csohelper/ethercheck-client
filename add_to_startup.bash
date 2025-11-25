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
SERVICE_NAME="internetmonitoring4.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"

# Log file (optional, for debugging)
LOG_FILE="$SCRIPT_DIR/startup_log.txt"

# Create the systemd service file
bash -c "cat > \"$SERVICE_PATH\" <<EOF
[Unit]
Description=Internet Monitoring Script

[Service]
ExecStart=$SCRIPT_DIR/run.bash
WorkingDirectory=$SCRIPT_DIR
Restart=always
User=$(whoami)

[Install]
WantedBy=multi-user.target
EOF"

# Reload systemd, enable, and start the service
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"

read -p "Press Enter to continue..."
