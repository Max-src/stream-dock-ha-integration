"""Onboards the throwaway Home Assistant from start-ha.sh with a made-up user,
adds the Stream Dock HA integration, and prints a long-lived token for the app.

Run with the test venv's Python: python e2e/onboard.py [--url http://127.0.0.1:8124]
The token is written to ~/ha-e2e/token.txt too. It only opens the test instance.
"""

import argparse
import asyncio
import json
import pathlib

import aiohttp

CLIENT = "http://127.0.0.1:8124/"


async def main(url: str) -> None:
    async with aiohttp.ClientSession() as http:
        async with http.get(f"{url}/api/onboarding") as r:
            steps = {s["step"]: s["done"] for s in await r.json()}
        if not steps.get("user"):
            body = {"client_id": CLIENT, "name": "E2E Tester", "username": "e2e",
                    "password": "e2e-password", "language": "en"}
            async with http.post(f"{url}/api/onboarding/users", json=body) as r:
                code = (await r.json())["auth_code"]
        else:
            # Already onboarded: log in the normal way.
            async with http.post(f"{url}/auth/login_flow", json={
                "client_id": CLIENT, "handler": ["homeassistant", None], "redirect_uri": CLIENT}) as r:
                flow = await r.json()
            async with http.post(f"{url}/auth/login_flow/{flow['flow_id']}", json={
                "client_id": CLIENT, "username": "e2e", "password": "e2e-password"}) as r:
                code = (await r.json())["result"]
        async with http.post(f"{url}/auth/token", data={
            "grant_type": "authorization_code", "code": code, "client_id": CLIENT}) as r:
            access = (await r.json())["access_token"]
        auth = {"Authorization": f"Bearer {access}"}
        for step, body in (("core_config", {}), ("analytics", {}), ("integration",
                           {"client_id": CLIENT, "redirect_uri": CLIENT})):
            if not steps.get(step):
                async with http.post(f"{url}/api/onboarding/{step}", json=body, headers=auth):
                    pass

        async with http.get(f"{url}/api/config/config_entries/entry", headers=auth) as r:
            entries = await r.json()
        if not any(e["domain"] == "stream_dock_ha" for e in entries):
            async with http.post(f"{url}/api/config/config_entries/flow",
                                 json={"handler": "stream_dock_ha"}, headers=auth) as r:
                flow = await r.json()
            if flow.get("type") == "form":
                async with http.post(f"{url}/api/config/config_entries/flow/{flow['flow_id']}",
                                     json={}, headers=auth) as r:
                    flow = await r.json()
            print("integration:", flow.get("type"), flow.get("title", flow.get("reason", "")))

        ws_url = url.replace("http", "ws", 1) + "/api/websocket"
        async with http.ws_connect(ws_url) as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": access})
            await ws.receive_json()
            await ws.send_json({"id": 1, "type": "auth/long_lived_access_token",
                                "client_name": "Stream Dock HA e2e", "lifespan": 30})
            token = (await ws.receive_json())["result"]
    path = pathlib.Path.home() / "ha-e2e" / "token.txt"
    path.write_text(token)
    print(json.dumps({"url": url, "token_file": str(path)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8124")
    asyncio.run(main(parser.parse_args().url))
