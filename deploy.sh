#!/bin/bash
cd /Users/administrator/Sites/friedutch-app
git pull origin main
pkill -f "python3.*app.py"
sleep 1
launchctl bootout gui/501 /Users/administrator/Library/LaunchAgents/friedutch.shopping.plist 2>/dev/null
sleep 1
launchctl bootstrap gui/501 /Users/administrator/Library/LaunchAgents/friedutch.shopping.plist
