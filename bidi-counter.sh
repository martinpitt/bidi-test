#!/bin/bash
# Call this with the BiDi websocket URL
set -eu
WS_URL="$1"

# start websocat
coproc websocat "$WS_URL"
trap "kill $COPROC_PID; wait $COPROC_PID || true" EXIT INT QUIT PIPE

bidi() {
    echo "--- Request: ---"
    echo "$1" | jq
    read -p "⏸️ "
    echo "$1" >&${COPROC[1]}

    echo "--- Response: ---"
    read -u ${COPROC[0]} response
    echo "$response" | jq || echo "$response"
    read -p "⏸️ "
}

echo "** get default context"
bidi '{"id": 0, "method": "script.getRealms", "params": {}}'
CONTEXT=$(echo "$response" | jq -r '.result.realms[0].context')

# https://w3c.github.io/webdriver-bidi/#command-browsingContext-navigate
echo "** go to our local page"
bidi '{"id": 1, "method": "browsingContext.navigate", "params": {"context": "'$CONTEXT'", "url": "http://localhost:8000"}}'

# https://w3c.github.io/webdriver-bidi/#command-browsingContext-locateNodes
echo "** locate counter add button"
bidi '{"id": 2, "method": "browsingContext.locateNodes", "params": {"context": "'$CONTEXT'", "locator": {"type": "css", "value": "#btn"}}}'
BTN=$(echo "$response" | jq -cr '.result.nodes[0]')

# https://w3c.github.io/webdriver-bidi/#command-input-performActions
echo "** click button"
bidi '{"id": 3, "method": "input.performActions", "params": {"context": "'$CONTEXT'", "actions": [{"id": "pointer-0", "type": "pointer", "parameters": {"pointerType": "mouse"}, "actions": [{"type": "pointerMove", "x": 0, "y": 0, "origin": {"type": "element", "element": '$BTN'}}, {"type": "pointerDown", "button": 0}, {"type": "pointerUp", "button": 0}]}]}}'

# https://w3c.github.io/webdriver-bidi/#command-script-evaluate
echo "** get counter, run a JS expression"
bidi '{"id": 4, "method": "script.evaluate", "params": {"expression": "document.querySelector('"'"'#count'"'"').textContent", "target": {"context": "'$CONTEXT'"}, "awaitPromise": true}}'
