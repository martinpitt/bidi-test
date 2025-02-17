#!/usr/bin/python3
# First, run "python3 -m http.server" in the directory that has index.html

import argparse
import asyncio
import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp


@dataclass
class BidiSession:
    ws_url: str
    session_url: str
    process: asyncio.subprocess.Process


class WebdriverBidi:
    def __init__(self, headless=False) -> None:
        self.headless = headless
        self.last_id = 0
        self.pending_commands: dict[int, asyncio.Future] = {}
        self.bidi_session: BidiSession | None = None
        self.future_wait_page_load = None
        self.top_context: str | None = None  # top-level browsingContext
        self.context: str | None  # currently selected context (top or iframe)

    async def start_bidi_session(self) -> None:
        raise NotImplementedError('must be implemented by concrete subclass')

    async def close_bidi_session(self) -> None:
        raise NotImplementedError('must be implemented by concrete subclass')

    async def close(self):
        assert self.bidi_session is not None
        logging.debug("cleaning up webdriver")

        self.task_reader.cancel()
        del self.task_reader
        await self.ws.close()
        await self.close_bidi_session()
        self.bidi_session.process.terminate()
        await self.bidi_session.process.wait()
        self.bidi_session = None
        await self.http_session.close()

    def ws_done_callback(self, future):
        for fut in self.pending_commands.values():
            fut.set_exception(RuntimeError("websocket closed"))
        if not future.cancelled():
            logging.error("ws_reader crashed: %r", future.result())

    async def start_session(self) -> None:
        self.http_session = aiohttp.ClientSession(raise_for_status=True)
        await self.start_bidi_session()
        assert self.bidi_session
        self.ws = await self.http_session.ws_connect(self.bidi_session.ws_url)
        self.task_reader = asyncio.create_task(self.ws_reader(self.ws), name="bidi_reader")
        self.task_reader.add_done_callback(self.ws_done_callback)

        await self.bidi("session.subscribe", events=[
            "log.entryAdded", "browsingContext.domContentLoaded",
        ])

        # wait for browser to initialize default context
        for _ in range(10):
            realms = (await self.bidi("script.getRealms"))["realms"]
            if len(realms) > 0:
                self.top_context = realms[0]["context"]
                self.context = self.top_context
                break
        else:
            raise TimeoutError("timed out waiting for default realm")

    async def __aenter__(self):
        await self.start_session()
        return self

    async def __aexit__(self, *_excinfo):
        if self.bidi_session is not None:
            await self.close()

    async def ws_reader(self, ws: aiohttp.client.ClientWebSocketResponse) -> None:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                logging.debug("ws TEXT → %r", data)
                if "id" in data and data["id"] in self.pending_commands:
                    logging.debug("ws_reader: resolving pending command %i", data["id"])
                    if data["type"] == "success":
                        result = data["result"]
                        if result.get("type") == "exception":
                            self.pending_commands[data["id"]].set_exception(
                                    RuntimeError(result["exceptionDetails"]["text"]))
                        else:
                            self.pending_commands[data["id"]].set_result(result)
                    else:
                        self.pending_commands[data["id"]].set_exception(
                            RuntimeError(f"{data['type']}: {data['message']}"))
                    del self.pending_commands[data["id"]]
                    continue

                if data["type"] == "event":
                    if data["method"] == "log.entryAdded":
                        log = data["params"]
                        logging.info(f"LogMessage: {log['type']} {log['level']} {log['text']}")
                        continue
                    if data["method"] == "browsingContext.domContentLoaded":
                        if self.future_wait_page_load:
                            logging.debug("page loaded: %r, resolving wait page load future", data["params"])
                            self.future_wait_page_load.set_result(data["params"]["url"])
                        else:
                            logging.debug("page loaded: %r (not awaited)", data["params"])
                        continue

                logging.warning("ws_reader: unhandled message %r", data)
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logging.error("BiDi failure: %s", msg)
                break

    async def bidi(self, method, **params) -> dict[str, Any]:
        """Send a Webdriver BiDi command and return the JSON response"""

        payload = json.dumps({"id": self.last_id, "method": method, "params": params})
        logging.debug("ws ← %r", payload)
        await self.ws.send_str(payload)
        future = asyncio.get_event_loop().create_future()
        self.pending_commands[self.last_id] = future
        self.last_id += 1
        # some calls can take very long (wait for condition);
        # safe-guard timeout for avoiding eternally hanging tests
        return await asyncio.wait_for(future, timeout=10)

    #
    # BiDi state tracking
    #

    async def switch_to_frame(self, name: str) -> None:
        frame = await self.locate(f"iframe[name='{name}']")
        cw = await self.bidi("script.callFunction",
                             functionDeclaration="f => f.contentWindow",
                             arguments=[frame],
                             awaitPromise=False,
                             target={"context": self.top_context})
        self.context = cw["result"]["value"]["context"]
        logging.debug("switch_to_frame(%s)", name)

    def switch_to_top(self) -> None:
        self.context = self.top_context
        logging.debug("switch_to_top")

    #
    # High-level helpers
    #

    async def locate(self, selector: str) -> str:
        r = await self.bidi("browsingContext.locateNodes", context=self.context,
                            locator={"type": "css", "value": selector})
        nodes = r["nodes"]
        if len(nodes) == 0:
            raise RuntimeError(f"no element found for {selector}")
        if len(nodes) > 1:
            raise RuntimeError(f"selector {selector} is ambiguous: {nodes}")
        logging.debug("locate(%s) = %r", selector, nodes[0])
        return nodes[0]

    async def mouse(self, selector: str, button: int = 0, click_count: int = 1) -> None:
        element = await self.locate(selector)

        actions = [{"type": "pointerMove", "x": 0, "y": 0, "origin": {"type": "element", "element": element}}]
        for _ in range(click_count):
            actions.append({"type": "pointerDown", "button": button})
            actions.append({"type": "pointerUp", "button": button})

        await self.bidi("input.performActions", context=self.context, actions=[
            {
                "id": "pointer-0",
                "type": "pointer",
                "parameters": {"pointerType": "mouse"},
                "actions": actions,
            }
        ])


class ChromiumBidi(WebdriverBidi):
    async def start_bidi_session(self) -> None:
        assert self.bidi_session is None

        session_args = {"capabilities": {
            "alwaysMatch": {
                "webSocketUrl": True,
                "goog:chromeOptions": {
                    # default works fine if you have /usr/bin/chromium-browser
                    # "binary": "/usr/lib64/chromium-browser/headless_shell",
                    "args": ["--headless"] if self.headless else [],
                },
            }
        }}

        driver = await asyncio.create_subprocess_exec("chromedriver", "--port=9515")
        wd_url = "http://localhost:9515"

        # webdriver needs some time to launch
        for retry in range(1, 10):
            try:
                async with self.http_session.post(f"{wd_url}/session",
                                                  data=json.dumps(session_args).encode()) as resp:
                    session_info = json.loads(await resp.text())["value"]
                    logging.debug("webdriver session request: %r %r", resp, session_info)
                    break
            except (IOError, aiohttp.client.ClientResponseError) as e:
                logging.debug("waiting for webdriver: %s", e)
                await asyncio.sleep(0.1 * retry)
        else:
            raise TimeoutError("could not connect to chromedriver")

        self.bidi_session = BidiSession(
            session_url=f"{wd_url}/session/{session_info['sessionId']}",
            ws_url=session_info["capabilities"]["webSocketUrl"],
            process=driver)
        logging.debug("Established chromium session %r", self.bidi_session)

    async def close_bidi_session(self):
        await self.http_session.delete(self.bidi_session.session_url)


# We could do this with https://github.com/mozilla/geckodriver/releases with a similar protocol as ChromeBidi
# But let's use https://firefox-source-docs.mozilla.org/testing/marionette/Protocol.html directly, fewer moving parts
class FirefoxBidi(WebdriverBidi):
    async def start_bidi_session(self) -> None:
        marionette_port = 9515
        bidi_port = 9516

        self.homedir = tempfile.TemporaryDirectory(prefix="firefox-home-")
        (Path(self.homedir.name) / 'download').mkdir()
        self.profiledir = Path(self.homedir.name) / "profile"
        self.profiledir.mkdir()
        (self.profiledir / "user.js").write_text(f"""
            // enable this to work around https://bugzilla.mozilla.org/show_bug.cgi?id=1947402
            // user_pref('remote.events.async.enabled', false);

            user_pref('remote.log.level', 'Trace');
            user_pref('remote.log.truncate', false);
            // enable remote logs on stdout
            user_pref('browser.dom.window.dump.enabled', true);

            user_pref("app.update.auto", false);
            user_pref("datareporting.policy.dataSubmissionEnabled", false);
            user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);
            user_pref("dom.disable_beforeunload", true);
            user_pref("browser.download.dir", "{self.homedir}/download");
            user_pref("browser.download.folderList", 2);
            user_pref("signon.rememberSignons", false);
            user_pref("dom.navigation.locationChangeRateLimit.count", 9999);
            user_pref('marionette.port', {marionette_port});
            """)

        driver = await asyncio.create_subprocess_exec(
            "firefox", "-profile", str(self.profiledir), "--marionette", "--no-remote",
            f"--remote-debugging-port={bidi_port}",
            *(["-headless"] if self.headless else []), "about:blank")

        # needs some time to launch
        for _ in range(1, 30):
            try:
                # we must keep this socket open throughout the lifetime of that session
                reader, self.writer_marionette = await asyncio.open_connection("127.0.0.1", marionette_port)
                break
            except ConnectionRefusedError as e:
                logging.debug("waiting for firefox marionette: %s", e)
                await asyncio.sleep(1)
        else:
            raise TimeoutError("could not connect to firefox marionette")

        reply = await reader.read(1024)
        if b'"marionetteProtocol":3' not in reply:
            raise RuntimeError(f"unexpected marionette reply: {reply.decode()}")
        cmd = '[0,1,"WebDriver:NewSession",{"webSocketUrl":true}]'
        self.writer_marionette.write(f"{len(cmd)}:{cmd}".encode())
        await self.writer_marionette.drain()
        reply = await reader.read(1024)
        # cut off length prefix
        reply = json.loads(reply[reply.index(b":") + 1:].decode())
        if not isinstance(reply, list) or len(reply) != 4 or not isinstance(reply[3], dict):
            raise RuntimeError(f"unexpected marionette session request reply: {reply!r}")
        logging.debug("marionette session request reply: %s", reply)

        url = reply[3]["capabilities"]["webSocketUrl"]
        self.bidi_session = BidiSession(session_url=url, ws_url=url, process=driver)
        logging.debug("Established firefox session %r", self.bidi_session)

    async def close_bidi_session(self):
        self.writer_marionette.close()
        await self.writer_marionette.wait_closed()


async def main():
    argparser = argparse.ArgumentParser()
    argparser.add_argument("-s", "--show-browser", action="store_true")
    argparser.add_argument("-f", "--firefox", action="store_true")
    argparser.add_argument("-d", "--debug", action="store_true")
    args = argparser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    cls = FirefoxBidi if args.firefox else ChromiumBidi

    async with cls(headless=not args.show_browser) as d:
        await d.bidi("browsingContext.navigate", context=d.context, url="http://localhost:8000/index.html",
                     wait="complete")
        await d.switch_to_frame("first")
        print("\n#### Clicking button")
        await d.mouse("#btn")
        await asyncio.sleep(0.5)
        d.switch_to_top()
        await d.switch_to_frame("second")


if __name__ == "__main__":
    asyncio.run(main())
