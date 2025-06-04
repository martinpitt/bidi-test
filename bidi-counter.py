#!/usr/bin/python3

import argparse
import asyncio
import logging
import sys

try:
    import webdriver_bidi
except ImportError:
    sys.exit("Needs: curl -O https://raw.githubusercontent.com/cockpit-project/cockpit/refs/heads/main/test/common/webdriver_bidi.py")


async def mouse(wd: webdriver_bidi.WebdriverBidi, selector: str, button: int = 0, click_count: int = 1) -> None:
    """High-level helper for a mouse event"""

    element = await wd.locate(selector)

    actions = [{"type": "pointerMove", "x": 0, "y": 0, "origin": {"type": "element", "element": element}}]
    for _ in range(click_count):
        actions.append({"type": "pointerDown", "button": button})
        actions.append({"type": "pointerUp", "button": button})

    await wd.bidi("input.performActions", context=wd.context, actions=[
        {
            "id": "pointer-0",
            "type": "pointer",
            "parameters": {"pointerType": "mouse"},
            "actions": actions,
        }
    ])


async def main():
    argparser = argparse.ArgumentParser()
    argparser.add_argument("-s", "--show-browser", action="store_true")
    argparser.add_argument("-f", "--firefox", action="store_true")
    argparser.add_argument("-d", "--debug", action="store_true")
    args = argparser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    cls = webdriver_bidi.FirefoxBidi if args.firefox else webdriver_bidi.ChromiumBidi

    async with cls(headless=not args.show_browser) as d:
        print("\n** go to our local page")
        await d.bidi("browsingContext.navigate",
                     context=d.context,
                     url="http://localhost:8000",
                     wait="complete")
        input("⏸️ ")

        print("\n** click add button")
        await mouse(d, "#btn")
        input("⏸️ ")

        print("\n** get counter, run a JS expression")
        reply = await d.bidi("script.evaluate",
                             expression="document.querySelector('#count').textContent",
                             target={"context": d.context},
                             awaitPromise=True)
        print(f"counter value: {reply['result']}")
        input("⏸️ ")


if __name__ == "__main__":
    asyncio.run(main())
