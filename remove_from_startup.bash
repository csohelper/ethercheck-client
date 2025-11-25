#!/bin/bash

# Service name and path
SERVICE_NAME="internetmonitoring4.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"

# Stop and disable the service if it exists
if [ -f "$SERVICE_PATH" ]; then
    sudo systemctl stop "$SERVICE_NAME"
    sudo systemctl disable "$SERVICE_NAME"
    sudo rm "$SERVICE_PATH"
    sudo systemctl daemon-reload
    echo "Service removed from startup."
else
    echo "Service not found in startup."
fi

echo "Operation completed."
read -p "Press Enter to continue..."
