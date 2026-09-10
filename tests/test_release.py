import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from scripts.render_release import render, ROOT
from scripts.deploy_dokploy import deploy


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tag = "dev-" + "a" * 40
        self.release = render("harbor.example.com/agri/pipeline", self.tag, "https://dev.example.com")

    def test_release_can_travel_without_checkout_or_local_secrets(self):
        encoded = json.dumps(self.release)
        self.assertNotIn('"build":', encoded)
        self.assertNotIn('"file":', encoded)
        self.assertNotIn('"ports":', encoded)
        self.assertNotIn('"name": "mahavistaar"', encoded)
        self.assertEqual(set(self.release["volumes"]), {"postgres-data", "minio-data", "qdrant-data"})
        images = [self.release["services"][s]["image"] for s in ("api", "worker", "db-init")]
        self.assertEqual(len(set(images)), 1)
        self.assertTrue(images[0].endswith(self.tag))
        for service in self.release["services"].values():
            for volume in service.get("volumes", []):
                self.assertFalse(volume.startswith((".", "/")), volume)
        self.assertEqual(self.release["services"]["keycloak"]["environment"]["KC_HOSTNAME"],
                         "https://dev.example.com/auth")

    def test_compose_interpolation_preserves_embedded_configuration(self):
        # $$ is unescaped by Compose before these files reach their consumers.
        config = self.release["configs"]
        self.assertEqual(config["postgres-init"]["content"].replace("$$", "$"),
                         (ROOT / "deploy/postgres-init.sh").read_text())
        realm = json.loads(config["keycloak-realm"]["content"].replace("$$", "$"))
        self.assertEqual(realm["users"][0]["credentials"][0]["value"], "${APP_ADMIN_PASSWORD}")
        self.assertEqual(realm["sslRequired"], "external")
        nginx = config["nginx-config"]["content"].replace("$$", "$")
        self.assertIn("X-Forwarded-Proto $forwarded_scheme", nginx)
        self.assertIn(f'X-Release-Sha "{self.tag}"', nginx)

    def test_invalid_release_inputs_fail_before_publication(self):
        for prefix, tag, origin in [
            ("https://harbor.example.com/agri/pipeline", self.tag, "https://dev.example.com"),
            ("harbor.example.com/agri/pipeline", "latest", "https://dev.example.com"),
            ("harbor.example.com/agri/pipeline", self.tag, "ftp://dev.example.com"),
            ("harbor.example.com/agri/pipeline", self.tag, "https://dev.example.com/"),
        ]:
            with self.subTest(prefix=prefix, tag=tag, origin=origin), self.assertRaises(ValueError):
                render(prefix, tag, origin)

    def test_deployment_preserves_secrets_and_rejects_old_release_health(self):
        old = MagicMock(status=200, headers={"X-Release-Sha": "old"})
        new = MagicMock(status=200, headers={"X-Release-Sha": self.tag})
        login = MagicMock(status=200)
        responses = []
        for response in (old, new, login):
            context = MagicMock()
            context.__enter__.return_value = response
            responses.append(context)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "release.json"
            path.write_text(json.dumps(self.release))
            with patch.dict(os.environ, {"DOKPLOY_URL": "https://dokploy.example.com",
                                         "DOKPLOY_API_KEY": "secret", "DOKPLOY_COMPOSE_ID": "service"}), \
                 patch("scripts.deploy_dokploy.api") as api, \
                 patch("scripts.deploy_dokploy.urlopen", side_effect=responses) as http, \
                 patch("scripts.deploy_dokploy.time.sleep") as sleep:
                api.side_effect = [{"sourceType": "raw", "composeType": "docker-compose"}, None, None]
                deploy(path)
                update = api.call_args_list[1].args[3]
                self.assertEqual(set(update), {"composeId", "composeFile", "createEnvFile", "autoDeploy"})
                self.assertEqual(api.call_args_list[2].args[2], "compose.deploy")
                self.assertFalse(api.call_args_list[2].args[3]["freshVolumes"])
                sleep.assert_called_once_with(10)
                self.assertEqual(http.call_count, 3)

    def test_refuses_to_overwrite_git_managed_service(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "release.json"
            path.write_text(json.dumps(self.release))
            with patch.dict(os.environ, {"DOKPLOY_URL": "https://dokploy.example.com",
                                         "DOKPLOY_API_KEY": "secret", "DOKPLOY_COMPOSE_ID": "service"}), \
                 patch("scripts.deploy_dokploy.api", return_value={"sourceType": "github"}) as api:
                with self.assertRaisesRegex(ValueError, "dedicated Raw"):
                    deploy(path)
                self.assertEqual(api.call_count, 1)


if __name__ == "__main__":
    unittest.main()
