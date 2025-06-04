#!/bin/sh
# Start a Chromium WebDriver BiDi session
set -eu

chromedriver --port=9515 &
DRIVER_PID=$!
trap "kill $DRIVER_PID" EXIT INT QUIT PIPE
sleep 1
WD_URL=http://localhost:9515/session

echo "Requesting a new Chrome window with a BiDi session"
# https://developer.mozilla.org/en-US/docs/Web/WebDriver/Reference/Capabilities
SESSION=$(curl -s --show-error --json '{"capabilities":{"alwaysMatch":{ "webSocketUrl": true }}}' $WD_URL)
echo "Session request reply:"
echo "$SESSION"

SESSION_ID=$(echo "$SESSION" | jq -r .value.sessionId)
SESSION_URL="$WD_URL/$SESSION_ID"
WSURL=$(echo "$SESSION" | jq -r '.value.capabilities.webSocketUrl')
echo
echo "BiDi websocket: $WSURL"

read -p "Run your test now, press Enter to clean up⏸️ "

echo "Closing BiDi session"
curl -X DELETE $SESSION_URL
