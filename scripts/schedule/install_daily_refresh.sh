#!/bin/bash
# Install a daily macOS launchd job that runs the incremental 13F refresh.
#
# Runs on this Mac because that is where SEC EDGAR is reachable; nothing needs
# the dashboard server or a browser open. Uses the python3 on your PATH right
# now, so activate the environment you normally use before running this.
#
#   scripts/schedule/install_daily_refresh.sh            # daily at 18:41
#   HOUR=7 MINUTE=12 scripts/schedule/install_daily_refresh.sh
#   DRY_RUN=1 scripts/schedule/install_daily_refresh.sh  # print the plist only
set -euo pipefail

LABEL="local.13f-monitoring.refresh"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="$(command -v python3)"
HOUR="${HOUR:-18}"
MINUTE="${MINUTE:-41}"
LOG_DIR="$ROOT/data/logs"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if ! "$PYTHON" -c "import requests" 2>/dev/null; then
  echo "The python3 on your PATH ($PYTHON) cannot import requests."
  echo "Activate the environment you run the dashboard with, then rerun."
  exit 1
fi
if ! grep -q '^SEC_USER_AGENT=' "$ROOT/.env" 2>/dev/null; then
  echo "No SEC_USER_AGENT in $ROOT/.env; the scheduled run would be refused by SEC."
  echo 'Add: SEC_USER_AGENT="13F Monitoring local dashboard <your email>"'
  exit 1
fi

PLIST_BODY="<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$ROOT/scripts/refresh_data.py</string>
    <string>--incremental</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MINUTE</integer></dict>
  <key>StandardOutPath</key><string>$LOG_DIR/refresh.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/refresh.log</string>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>"

if [ -n "${DRY_RUN:-}" ]; then
  echo "$PLIST_BODY"
  exit 0
fi

mkdir -p "$LOG_DIR" "$(dirname "$PLIST")"
printf '%s\n' "$PLIST_BODY" > "$PLIST"
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

printf 'Installed %s: runs daily at %02d:%02d.\n' "$LABEL" "$HOUR" "$MINUTE"
echo "If the Mac is asleep then, it runs on wake."
echo "Run it now:   launchctl kickstart -k gui/$(id -u)/$LABEL"
echo "Watch it:     tail -f \"$LOG_DIR/refresh.log\""
echo "Remove it:    scripts/schedule/uninstall_daily_refresh.sh"
