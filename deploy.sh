#!/bin/bash
cd /Users/administrator/Sites/friedutch-app
git pull origin main
launchctl bootout gui/$(id -u) /Users/administrator/Library/LaunchAgents/friedutch.shopping.plist
sleep 2
launchctl bootstrap gui/$(id -u) /Users/administrator/Library/LaunchAgents/friedutch.shopping.plist
