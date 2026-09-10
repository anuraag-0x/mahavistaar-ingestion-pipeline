"""Render a self-contained Dokploy Raw Compose release without reading secrets."""

import argparse
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]


def render(image_prefix: str, image_tag: str, app_origin: str) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9.:-]*(/[a-z0-9][a-z0-9._-]*)+", image_prefix):
        raise ValueError("Image prefix must be registry/project/repository in lowercase")
    if not re.fullmatch(r"(?:dev|main)-[0-9a-f]{40}", image_tag):
        raise ValueError("Image tag must be dev-<full SHA> or main-<full SHA>")
    origin = urlsplit(app_origin)
    if (origin.scheme not in ("http", "https") or not origin.hostname or origin.path
            or origin.query or origin.fragment or origin.username or origin.password):
        raise ValueError("APP_ORIGIN must be an HTTP(S) origin without a trailing slash")
    compose = yaml.safe_load((ROOT / "compose.dokploy.yaml").read_text())
    compose.pop("x-backend")
    for name in ("api", "worker", "db-init"):
        compose["services"][name]["image"] = f"{image_prefix}-backend:{image_tag}"
        compose["services"][name]["environment"]["KEYCLOAK_ISSUER"] = (
            app_origin + "/auth/realms/docs-pipeline"
        )
        compose["services"][name]["environment"]["CORS_ORIGINS"] = app_origin
    compose["services"]["frontend"]["image"] = f"{image_prefix}-frontend:{image_tag}"
    keycloak_env = compose["services"]["keycloak"]["environment"]
    keycloak_env["APP_ORIGIN"] = app_origin
    keycloak_env["KC_HOSTNAME"] = app_origin + "/auth"
    for name, config in compose["configs"].items():
        content = (ROOT / config.pop("file")).read_text()
        if name == "nginx-config":
            content = content.replace("__RELEASE_SHA__", image_tag)
        elif name == "keycloak-realm":
            realm = json.loads(content)
            realm["sslRequired"] = "external" if origin.scheme == "https" else "none"
            content = json.dumps(realm, indent=2)
        # Compose must leave Nginx/shell variables and Keycloak placeholders intact.
        config["content"] = content.replace("$", "$$")
    return compose


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-prefix", required=True)
    parser.add_argument("--image-tag", required=True)
    parser.add_argument("--app-origin", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    release = render(args.image_prefix, args.image_tag, args.app_origin)
    # JSON is valid YAML, avoids YAML aliases, and preserves embedded config text.
    args.output.write_text(json.dumps(release, indent=2) + "\n")


if __name__ == "__main__":
    main()
