# WebDriver BiDi test / bug reproducer

This is a proof of concept of talking [BiDi](https://w3c.github.io/webdriver-bidi/) to Chromium or Firefox.

In particular, this reproduces https://bugzilla.mozilla.org/show_bug.cgi?id=1947402 where
sending a mouse click sometimes does not get a response.

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
