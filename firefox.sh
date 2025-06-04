#!/bin/sh
# Start a Firefox WebDriver BiDi session
# We could do this with https://github.com/mozilla/geckodriver/releases with a similar protocol as chromedriver
# But let's use https://firefox-source-docs.mozilla.org/testing/marionette/Protocol.html directly, fewer moving parts

set -eu

# create Firefox profile
profile_dir=$(mktemp -d)

cat << EOF > "$profile_dir/user.js"
// set this to "Trace" for debugging BiDi interactions
user_pref('remote.log.level', 'Warn');
user_pref('remote.log.truncate', false);
// enable remote logs on stdout
user_pref('browser.dom.window.dump.enabled', true);

user_pref('marionette.port', 9515);
EOF

# can append -headless here if desired
firefox -profile "$profile_dir" --marionette --no-remote --remote-debugging-port=9516 about:blank &
FIREFOX_PID=$!
sleep 1

echo "Requesting a Firefox BiDi session"
# we need to keep the marionette socket open throughout the lifetime of that session
# this line is an utter hack, this needs Python for properly speaking that protocol
{ echo '50:[0,1,"WebDriver:NewSession",{"webSocketUrl":true}]'; sleep infinity; } | nc 127.0.0.1 9515 > "$profile_dir/marionette" &
NC_PID=$!
trap "kill $FIREFOX_PID $NC_PID; rm -rf $profile_dir" EXIT INT QUIT PIPE
sleep 1

WSURL=$(grep -o 'ws://[^"]*' "$profile_dir/marionette")

echo "BiDi websocket: $WSURL"

read -p "Run your test now, press Enter to clean up⏸️ "
