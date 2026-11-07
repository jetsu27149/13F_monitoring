#!/bin/bash
# Remove the daily launchd refresh job installed by install_daily_refresh.sh.
set -euo pipefail
LABEL="local.13f-monitoring.refresh"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "Removed $LABEL. Downloaded data and logs are untouched."
