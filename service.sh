#!/bin/bash

PLIST="$HOME/Library/LaunchAgents/com.tuya.exporter.plist"
LABEL="com.tuya.exporter"

case "$1" in
  start)
    launchctl load "$PLIST"
    echo "Started $LABEL"
    ;;
  stop)
    launchctl unload "$PLIST"
    echo "Stopped $LABEL"
    ;;
  restart)
    launchctl unload "$PLIST" 2>/dev/null
    launchctl load "$PLIST"
    echo "Restarted $LABEL"
    ;;
  status)
    launchctl list | grep "$LABEL"
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}"
    exit 1
    ;;
esac
