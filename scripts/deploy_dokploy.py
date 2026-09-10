"""Publish a rendered release to a dedicated Dokploy Raw Compose service."""

import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


def api(base, token, method, payload, *, read=False):
    url = f"{base}/api/{method}"
    if read:
        url += "?" + urlencode(payload)
    request = Request(
        url,
        data=None if read else json.dumps(payload).encode(),
        headers={"x-api-key": token, "Content-Type": "application/json"},
        method="GET" if read else "POST",
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read() or "null")


def deploy(release_path):
    base = os.environ["DOKPLOY_URL"].rstrip("/")
    if urlsplit(base).scheme != "https":
        raise ValueError("DOKPLOY_URL must use HTTPS")
    token = os.environ["DOKPLOY_API_KEY"]
    compose_id = os.environ["DOKPLOY_COMPOSE_ID"]
    release_text = Path(release_path).read_text()
    release = json.loads(release_text)
    image_tag = release["services"]["api"]["image"].rsplit(":", 1)[1]
    origin = release["services"]["api"]["environment"]["CORS_ORIGINS"]
    current = api(base, token, "compose.one", {"composeId": compose_id}, read=True)
    if current.get("sourceType") != "raw" or current.get("composeType") != "docker-compose":
        raise ValueError("Target must be a dedicated Raw Docker Compose service")
    if current.get("composeStatus") == "running":
        raise ValueError("A deployment is already running; retry after it finishes")
    api(base, token, "compose.update", {
        "composeId": compose_id, "composeFile": release_text,
        "createEnvFile": True, "autoDeploy": False,
    })
    # Runtime secrets, appName (volume identity), domains, and registry settings
    # belong to the service and are deliberately omitted from the update.
    api(base, token, "compose.deploy", {
        "composeId": compose_id, "title": image_tag, "freshVolumes": False,
    })
    print(f"Deployment requested for {image_tag}; waiting for application health and login.", flush=True)
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        try:
            request = Request(origin + "/health", headers={"Cache-Control": "no-cache"})
            with urlopen(request, timeout=15) as response:
                matched = (response.status == 200
                           and response.headers.get("X-Release-Sha") == image_tag)
            if matched:
                with urlopen(origin + "/login", timeout=15) as response:
                    if response.status == 200:
                        print("Release gateway/API health and frontend login checks passed.")
                        return
        except (HTTPError, URLError, TimeoutError):
            pass
        time.sleep(10)
    raise RuntimeError("Release did not become healthy within 10 minutes; inspect Dokploy logs")


if __name__ == "__main__":
    try:
        deploy(sys.argv[1])
    except HTTPError as error:
        # Do not print API response bodies, which may contain service secrets.
        sys.exit(f"Dokploy HTTP request failed ({error.code}); inspect the service logs")
