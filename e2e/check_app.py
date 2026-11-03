"""End-to-end check of the real app against the throwaway Home Assistant.

Run it in WSL with the venv's Python while a sandboxed copy of the app is
connected (STREAM_DOCK_HA_SANDBOX, with a dashboard pad whose first key toggles
input_boolean.desk_lamp, whose third key opens a program, and whose page 2
exists):

    ~/venvs/stream-dock-ha/bin/python e2e/check_app.py            # while the app runs
    ~/venvs/stream-dock-ha/bin/python e2e/check_app.py --offline  # after the app is stopped

It only uses the test instance at 127.0.0.1:8124 and its token in
~/ha-e2e/token.txt. It prints what it sees and exits non-zero on the first
check that fails.
"""

from __future__ import annotations

import asyncio
import base64
import itertools
import json
import os
import struct
import sys
from pathlib import Path

import aiohttp

URL = os.environ.get("HA_E2E_URL", "ws://127.0.0.1:8124/api/websocket")
TOKEN = Path(os.environ.get("HA_E2E_TOKEN_FILE", Path.home() / "ha-e2e" / "token.txt")).read_text().strip()
LAMP = "input_boolean.desk_lamp"


def check(ok: bool, what: str) -> None:
    print(("PASS " if ok else "FAIL ") + what, flush=True)
    if not ok:
        sys.exit(1)


def jpeg_size(data: bytes) -> tuple[int, int]:
    """Width and height from a JPEG's frame header."""
    assert data[:2] == b"\xff\xd8", "not a JPEG"
    at = 2
    while at < len(data):
        marker, length = data[at + 1], struct.unpack(">H", data[at + 2 : at + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2):
            height, width = struct.unpack(">HH", data[at + 5 : at + 9])
            return width, height
        at += 2 + length
    raise ValueError("no frame header")


class Ha:
    """One logged-in WebSocket connection, with events kept per subscription."""

    def __init__(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        self.ws = ws
        self.ids = itertools.count(1)
        self.waiting: dict[int, asyncio.Future] = {}
        self.events: dict[int, asyncio.Queue] = {}
        self.reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        async for message in self.ws:
            data = json.loads(message.data)
            if data["type"] == "result" and data["id"] in self.waiting:
                self.waiting.pop(data["id"]).set_result(data)
            elif data["type"] == "event" and data["id"] in self.events:
                await self.events[data["id"]].put(data["event"])

    async def call(self, message: dict, timeout: float = 15) -> dict:
        number = next(self.ids)
        future = asyncio.get_running_loop().create_future()
        self.waiting[number] = future
        if message["type"] in ("stream_dock_ha/watch", "subscribe_events"):
            self.events[number] = asyncio.Queue()
        await self.ws.send_json({**message, "id": number})
        result = await asyncio.wait_for(future, timeout)
        result["_id"] = number
        return result

    async def ok(self, message: dict) -> object:
        result = await self.call(message)
        if not result["success"]:
            raise RuntimeError(f"{message['type']} refused: {result['error']}")
        return result.get("result")

    async def event(self, subscription: int, want, timeout: float = 15) -> dict:
        """The next event on a subscription that `want` accepts."""
        queue = self.events[subscription]
        async with asyncio.timeout(timeout):
            while True:
                event = await queue.get()
                if want(event):
                    return event

    async def state(self, entity_id: str) -> dict | None:
        states = await self.ok({"type": "get_states"})
        return next((s for s in states if s["entity_id"] == entity_id), None)

    async def service(self, domain: str, service: str, data: dict, response: bool = False) -> dict:
        message = {"type": "call_service", "domain": domain, "service": service, "service_data": data}
        if response:
            message["return_response"] = True
        return await self.call(message)


async def connect(session: aiohttp.ClientSession) -> Ha:
    ws = await session.ws_connect(URL, max_msg_size=0)
    assert (await ws.receive_json())["type"] == "auth_required"
    await ws.send_json({"type": "auth", "access_token": TOKEN})
    reply = await ws.receive_json()
    check(reply["type"] == "auth_ok", f"logged in to Home Assistant {reply.get('ha_version')}")
    return Ha(ws)


async def our_pad(ha: Ha) -> dict:
    pads = (await ha.ok({"type": "stream_dock_ha/pads"}))["pads"]
    print("  pads:", [(p["name"], p["pc"], p["kind"], p["online"]) for p in pads])
    pad = next((p for p in pads if p["kind"] == "dashboard" and p["pc"] == "E2E Sandbox PC"), None)
    check(pad is not None, "the sandbox PC's dashboard pad is listed by stream_dock_ha/pads")
    return pad


async def entities_of(ha: Ha, device_ids: set[str]) -> list[dict]:
    registry = await ha.ok({"type": "config/entity_registry/list"})
    return [e for e in registry if e.get("device_id") in device_ids]


async def wait_for(what, timeout: float = 10, step: float = 0.25):
    async with asyncio.timeout(timeout):
        while True:
            found = await what()
            if found:
                return found
            await asyncio.sleep(step)


async def online() -> None:
    async with aiohttp.ClientSession() as session:
        ha = await connect(session)
        pad = await our_pad(ha)
        check(pad["online"], "the pad is online")

        devices = await ha.ok({"type": "config/device_registry/list"})
        ours = [d for d in devices if any(i[0] == "stream_dock_ha" for i in d["identifiers"])]
        print("  devices:", [(d["name"], d["model"], d["via_device_id"] is not None) for d in ours])
        pc = next(d for d in ours if d["id"] != pad["device_id"] and d["name"] == "E2E Sandbox PC")
        check(any(d["id"] == pad["device_id"] and d["via_device_id"] == pc["id"] for d in ours), "a PC device and the pad's device under it")
        entities = await entities_of(ha, {pc["id"], pad["device_id"]})
        ids = sorted(e["entity_id"] for e in entities)
        print("  entities:", ids)
        states = {s["entity_id"]: s for s in await ha.ok({"type": "get_states"})}
        profile = next(i for i in ids if i.startswith("select."))
        page = next(i for i in ids if i.startswith("number."))
        screen = next(i for i in ids if i.startswith("light."))
        check(states[profile]["state"] == "Wall" and states[page]["state"] in ("1", "1.0"), f"{profile} is Wall and {page} is 1")
        check(states[screen]["state"] == "on", f"{screen} is on")

        # Start from a lit pad with no alert, whatever an earlier run left.
        await ha.service("stream_dock_ha", "clear_alert", {"device_id": pad["device_id"]})
        await ha.service("stream_dock_ha", "set_screen", {"device_id": pad["device_id"], "on": True})

        # A press from an action toggles the lamp through the app.
        before = (await ha.state(LAMP))["state"]
        result = await ha.service("stream_dock_ha", "press_key", {"device_id": pad["device_id"], "key": 1})
        check(result["success"], f"stream_dock_ha.press_key answered: {result.get('error')}")
        after = await wait_for(lambda: _changed(ha, before))
        check(after != before, f"the desk lamp went {before} -> {after} from press_key")

        # show_page moves the page entity.
        result = await ha.service("stream_dock_ha", "show_page", {"device_id": pad["device_id"], "page": 2})
        check(result["success"], "stream_dock_ha.show_page answered")
        await wait_for(lambda: _is(ha, page, ("2", "2.0")))
        check(True, f"{page} followed to 2")
        await ha.service("stream_dock_ha", "show_page", {"device_id": pad["device_id"], "page": 1})
        await wait_for(lambda: _is(ha, page, ("1", "1.0")))

        # A card watches the pad and gets real pictures.
        watch = await ha.call({"type": "stream_dock_ha/watch", "pad_id": pad["pad_id"], "scale": 2})
        check(watch["success"], "stream_dock_ha/watch accepted")
        first = await ha.event(watch["_id"], lambda e: e["kind"] == "pad")
        check(first["online"] and first["pad"]["kind"] == "dashboard", "the watch starts with the pad's state")
        # The integration first replays the set it holds, which can be older
        # (pictures aren't sent while nobody watches); the app's own complete
        # set follows straight away.
        pictures = await ha.event(watch["_id"], lambda e: e["kind"] == "pictures" and e["pictures"].get("key_1") and e["pictures"].get("key_6", 0) is None)
        key = pictures["pictures"]["key_1"]
        size = jpeg_size(base64.b64decode(key["data"]))
        print(f"  pictures: scale {pictures['scale']}, controls {sorted(pictures['pictures'])}, key_1 is {size}")
        check(size == (170, 170), "key_1 is a real 170x170 JPEG at scale 2")
        check(pictures["pictures"].get("key_6", "absent") is None, "an empty key is null")

        # Whatever else is on its way settles first, so the press's own change is what's seen.
        await asyncio.sleep(1)
        while not ha.events[watch["_id"]].empty():
            e = ha.events[watch["_id"]].get_nowait()
            if e["kind"] == "pictures" and e["pictures"].get("key_1"):
                key = e["pictures"]["key_1"]

        # The card's own press toggles it back, and the press event says so.
        presses = await ha.call({"type": "subscribe_events", "event_type": "stream_dock_ha_event"})
        before = (await ha.state(LAMP))["state"]
        pressed = await ha.call({"type": "stream_dock_ha/press", "pad_id": pad["pad_id"], "control": "key_1"})
        check(pressed["success"], f"stream_dock_ha/press answered {pressed.get('result') or pressed.get('error')}")
        after = await wait_for(lambda: _changed(ha, before))
        check(after != before, f"the desk lamp went {before} -> {after} from the card")
        event = await ha.event(presses["_id"], lambda e: e["data"].get("control") == "key_1")
        check(event["data"]["source"] == "dashboard" and not event["data"]["dismissed"], f"stream_dock_ha_event: {event['data']}")
        changed = await ha.event(watch["_id"], lambda e: e["kind"] == "pictures" and "key_1" in e["pictures"] and not e["complete"])
        check(changed["pictures"]["key_1"]["hash"] != key["hash"], f"only what changed came again: {sorted(changed['pictures'])}")

        # A key that opens a program can't be pressed from Home Assistant.
        refused = await ha.call({"type": "stream_dock_ha/press", "pad_id": pad["pad_id"], "control": "key_3"})
        check(not refused["success"], f"a key that opens a program is refused: {refused.get('error')}")

        # An alert covers the keys, and the next press only dismisses it.
        result = await ha.service("stream_dock_ha", "show_alert", {"device_id": pad["device_id"], "title": "Doorbell", "message": "Someone is at the door", "color": [200, 40, 40]})
        check(result["success"], "stream_dock_ha.show_alert answered")
        # The pictures come at once and the state a moment later, in either order.
        seen: dict[str, dict] = {}

        def alerting(e: dict) -> bool:
            if e["kind"] == "pad" and e["pad"]["alert"]:
                seen["pad"] = e
            if e["kind"] == "pictures" and len([v for v in e["pictures"].values() if v]) >= 6:
                seen["pictures"] = e
            return len(seen) == 2

        await ha.event(watch["_id"], alerting)
        check(seen["pad"]["pad"]["alert"], "the pad's state says alert")
        covered = seen["pictures"]
        print(f"  alert pictures: {sorted(covered['pictures'])}")
        check(all(v for v in covered["pictures"].values()), "every screen key shows its part of the alert")
        before = (await ha.state(LAMP))["state"]
        pressed = await ha.call({"type": "stream_dock_ha/press", "pad_id": pad["pad_id"], "control": "key_1"})
        check(pressed["success"] and pressed["result"].get("dismissed"), f"the press dismissed the alert: {pressed.get('result')}")
        await asyncio.sleep(1)
        check((await ha.state(LAMP))["state"] == before, "and didn't toggle the lamp")
        event = await ha.event(presses["_id"], lambda e: e["data"].get("dismissed"))
        check(True, f"stream_dock_ha_event for the dismissal: {event['data']}")

        # The screen light turns the pad dark, and its pictures go null.
        await ha.service("light", "turn_off", {"entity_id": screen})
        await wait_for(lambda: _is(ha, screen, ("off",)))
        dark = await ha.event(watch["_id"], lambda e: e["kind"] == "pictures" and e["pictures"] and all(v is None for v in e["pictures"].values()))
        check(True, f"{screen} off made every picture null ({len(dark['pictures'])} controls)")
        await ha.service("light", "turn_on", {"entity_id": screen})
        await wait_for(lambda: _is(ha, screen, ("on",)))
        check(True, f"{screen} came back on")

        # The picture entity's snapshot is a whole-pad JPEG.
        snap = await ha.service("stream_dock_ha", "get_state", {"device_id": pad["device_id"]}, response=True)
        check(snap["success"], "stream_dock_ha.get_state answered")
        last_press = (await ha.state(next(i for i in ids if i.endswith("last_press"))) or {}).get("state")
        check(last_press not in (None, "unknown", "unavailable"), f"the PC's last press is {last_press}")
        mic = next((i for i in ids if "microphone" in i or "mic" in i), None)
        print(f"  {mic}: {(await ha.state(mic) or {}).get('state') if mic else 'none'}")
        await ha.ws.close()


async def _changed(ha: Ha, before: str):
    state = (await ha.state(LAMP))["state"]
    return state if state != before else None


async def _is(ha: Ha, entity_id: str, wanted: tuple[str, ...]):
    state = await ha.state(entity_id)
    return state and state["state"] in wanted


async def offline() -> None:
    async with aiohttp.ClientSession() as session:
        ha = await connect(session)
        pad = await our_pad(ha)
        check(not pad["online"], "the pad shows offline once the app is gone")
        devices = await ha.ok({"type": "config/device_registry/list"})
        pc = next(d for d in devices if d["name"] == "E2E Sandbox PC" and any(i[0] == "stream_dock_ha" for i in d["identifiers"]))
        entities = await entities_of(ha, {pc["id"], pad["device_id"]})
        states = {s["entity_id"]: s["state"] for s in await ha.ok({"type": "get_states"})}
        shown = {e["entity_id"]: states.get(e["entity_id"]) for e in entities if e["entity_id"] in states}
        print("  states:", shown)
        online_sensor = [i for i in shown if i.endswith("_online") or i.endswith("online")]
        others = [i for i in shown if i not in online_sensor]
        check(all(shown[i] == "unavailable" for i in others), "every entity but Online is unavailable")
        check(all(shown[i] == "off" for i in online_sensor), "Online is off")
        await ha.ws.close()


if __name__ == "__main__":
    asyncio.run(offline() if "--offline" in sys.argv else online())
