# WebDriver BiDi test / bug reproducer

This is a proof of concept of talking [BiDi](https://w3c.github.io/webdriver-bidi/) to Chromium or Firefox.

In particular, this provides a reproducer for emulated mouse events not working
in Chromium when trying to click on an element in an iframe (it does work in
the top-level frame).

## Usage

First, start a local web server to serve the HTML pages:

```sh
python3 -m http.server &
```

Then run the reproducer:

```sh
./bidimouse.py
```

You can choose between Chromium (default) or Firefox (`-f`), show the browser
with `-s` (default is headless), and enable verbose logging with `-d`. See
`./bidimouse.py --help` for an overview of the options.

## Demo structure

`index.html` console-logs clicks on anywhere in its body, and embeds an iframe
at x = 100 and y roughly 180 (this depends on font size etc. of the h1).
`frame.html` has a button (at roughly x - 73 and y = 80) which logs clicks, and
also logs clicks anywhere in the body.

## Bug

When loading only `frame.html` directly, clicking the button with
[input.performActions](https://w3c.github.io/webdriver-bidi/#command-input-performActions)
works fine. `bidimouse.py` does the click correctly in both Chromium and
Firefox:

```
#### Clicking button
INFO:root:LogMessage: console info btn clicked @ 104 92
INFO:root:LogMessage: console info frame body clicked @ 104 92
```

But in the scenario where it loads `index.html`, and then switches context to
the embedded iframe, the button never receives the click. The coordinate is
apparently right, though:

```
#### Clicking button
INFO:root:LogMessage: console info toplevel body clicked @ 105 89
```

It works correctly with Firefox (same message as above with directly loading
`frame.html`)
