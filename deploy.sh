#!/bin/bash
cd /Users/administrator/Sites/friedutchplus
git pull origin main
pkill -f "python3.*server.py"
sleep 1
launchctl bootout gui/501 /Users/administrator/Library/LaunchAgents/friedutch.server.plist 2>/dev/null
sleep 1
launchctl bootstrap gui/501 /Users/administrator/Library/LaunchAgents/friedutch.server.plist
