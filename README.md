# Mahavistaar HTML deployment POC

One static HTML page served by Nginx. No application secrets, database,
Node.js installation, registry account, or build-time environment variables.

## Upload to GitHub

Upload the contents of this folder to the root of your personal repository
and commit to `main`. The repository root should contain `index.html`,
`Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env`, `.env.example`,
and this README. Both environment files contain only a non-secret port setting.
The Dockerfile copies only `index.html`; deployment also works if your
browser does not include the hidden `.dockerignore` file.

## Deploy through Dokploy

1. On the server, check that TCP port 9081 is free:

   ```bash
   sudo ss -ltnp | grep -E ':9081\b'
   ```

   No matching output means no TCP listener was found. If occupied, choose
   a free port and set `POC_HTTP_PORT` in the Compose service Environment tab.
2. Open the `mahavistaar-poc` Compose service in Dokploy.
3. Choose Docker Compose mode and the GitHub source.
4. Select `anuraag-0x/mahavistaar-ingestion-pipeline`, branch `main`, and
   Compose path `./docker-compose.yml`.
5. Replace any old application environment variables in this POC service
   with the contents of the supplied `.env`:

   ```dotenv
   POC_HTTP_PORT=9081
   ```

   Dokploy can generate its own `.env`, so set this in its Environment tab
   even if you uploaded the file. Leave Auto Deploy disabled for the first test.
6. Save and click Deploy. Inspect the deployment log for success.
7. Open `http://192.168.69.67:9081` from a machine that can reach the server.
   Use your chosen port if you changed `POC_HTTP_PORT`.

This POC publishes its own HTTP port directly. It does not need a Dokploy
domain, Traefik routing, or HTTPS configuration. The dashboard remains on
port 3100; Traefik's ports 9080 and 9443 are separate.

If the page cannot be reached, test on the server first:

```bash
curl -I http://127.0.0.1:9081
```

## Test an update

Change `Version 1.0` in `index.html` to `Version 1.1`, commit to `main`,
and click Deploy again. Refresh the browser to verify the new version.

Manual deployment verifies GitHub fetching and server builds. Automatic
deployment is a separate step: GitHub webhooks cannot directly reach this
private server address without additional connectivity.
