#!/bin/sh
set -eux

[ -d node_modules ] || npm install

python3 -m http.server &
HTTP_PID=$!
chromium-browser --remote-debugging-port=9222 &
CHROMIUM_PID=$!
sleep 1
trap "kill $CHROMIUM_PID $HTTP_PID" EXIT INT QUIT PIPE

(
# echo 'Log.enable()'
# echo 'Log.entryAdded(e => console.log("LOG:", e.entry.level, e.entry.text))'
echo 'Runtime.enable()'
echo 'Runtime.consoleAPICalled(e => console.log("CONSOLE:", e.type, JSON.stringify(e.args.map(i => i.value))))'

echo 'Page.navigate({url: "http://localhost:8000/frame.html"})'
sleep 2

echo >&2
echo '##### Directly loading frame' >&2

# click frame
echo 'Input.dispatchMouseEvent({type: "mousePressed", button: "left", x: 48, y: 38, clickCount: 1})'
echo 'Input.dispatchMouseEvent({type: "mouseReleased", button: "left", x: 48, y: 38, clickCount: 1})'
sleep 1

# click button
echo 'Input.dispatchMouseEvent({type: "mousePressed", button: "left", x: 104, y: 89, clickCount: 1})'
echo 'Input.dispatchMouseEvent({type: "mouseReleased", button: "left", x: 104, y: 89, clickCount: 1})'

echo >&2
echo '##### Loading toplevel with embedded iframe' >&2

echo 'Page.navigate({url: "http://localhost:8000/index.html"})'
sleep 2

# click top-level heading
echo 'Input.dispatchMouseEvent({type: "mousePressed", button: "left", x: 45, y: 30, clickCount: 1})'
echo 'Input.dispatchMouseEvent({type: "mouseReleased", button: "left", x: 45, y: 30, clickCount: 1})'

# click into iframe background
echo 'Input.dispatchMouseEvent({type: "mousePressed", button: "left", x: 120, y: 220, clickCount: 1})'
echo 'Input.dispatchMouseEvent({type: "mouseReleased", button: "left", x: 120, y: 220, clickCount: 1})'

# click on button in iframe
echo 'Input.dispatchMouseEvent({type: "mousePressed", button: "left", x: 220, y: 270, clickCount: 1})'
echo 'Input.dispatchMouseEvent({type: "mouseReleased", button: "left", x: 220, y: 270, clickCount: 1})'
sleep 1
) | node_modules/.bin/chrome-remote-interface inspect
