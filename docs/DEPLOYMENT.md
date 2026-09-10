# Docker deployment

The stack starts with one command from the repository root:

```bash
docker compose up -d --build --wait --wait-timeout 300
```

It runs Next.js, FastAPI, the ingestion worker, PostgreSQL, MinIO, and
Keycloak. Nginx runs on the host, not in Compose. Qdrant, OCR, translation, and
embedding endpoints are external services reached over the network.

## Prepare the server once

1. Install Docker Engine and the Docker Compose v2 plugin on the Linux server.
   Verify `docker compose version`. On Windows/WSL, use
   `wsl.exe -d Ubuntu -- docker compose ...` from the WSL-mounted checkout.
2. Check out this branch and create the root `.env` on the server. Keep `.env`
   only on the server; do not commit it.
3. Set `APP_ORIGIN` to the exact browser-facing origin, without a trailing slash.
   Set `MINIO_CONSOLE_URL` to `http://<server-ip>:9001`.
4. Set the local PostgreSQL credentials in `.env`. Compose creates the
   `docs-pipeline` application database and a separate
   `docs-pipeline-keycloak` database automatically on first startup. The
   PostgreSQL data is retained in the `postgres-data` named volume.
5. Fill in the MinIO credentials, Keycloak bootstrap administrator credentials,
   and initial application administrator credentials. Use single quotes around
   `.env` passwords containing `$` or `#`. The MinIO secret needs at least eight
   characters. The initial application account receives `super_admin`.
6. Set the Mistral OCR key, the existing embedding service base URL (serving
   `/v1/embeddings`), and the translation provider URL/model or Cerebras key.
   `localhost` inside a container is that container, not your host or AI server.
7. Allow access to port 80 for the application and port 9001 for the MinIO
   console from the intended network. Open port 443 as well when serving the
   public domain. Run the startup command above.

Required blank values produce an error before Compose creates services.
Changing `APP_ORIGIN` requires a frontend rebuild. The imported Keycloak realm
is created only on first startup; later origin or account changes must also be
made in the Keycloak admin console. Do not drop its database to change settings.

## URLs and ports

| Component | Browser URL / internal address |
| --- | --- |
| Application | `http://<server-ip>/`, `https://<domain>/` with TLS enabled |
| Backend Swagger | `<origin>/api/docs` |
| API requests and SSE | `<origin>/api/...` |
| Keycloak admin console | `<origin>/auth/admin/` |
| MinIO web console | `http://<server-ip>:9001` |
| MinIO S3 API | `minio:9000`, internal Docker network only |
| FastAPI | `127.0.0.1:8002` on the host, behind Nginx |
| Next.js | `127.0.0.1:3000` on the host, behind Nginx |
| Qdrant | external server, see `QDRANT_URL` |
| PostgreSQL | `postgres:5432`, internal Docker network only |

Sign into the application using `APP_ADMIN_USERNAME` / `APP_ADMIN_PASSWORD`.
The Keycloak bootstrap administrator is a separate account for identity
administration. Google SSO and email OTP remain hidden in the existing UI.
The new deployment realm contains no exported development users or secrets.

The base file serves HTTP only. See "Enable TLS" below to put the stack behind
`https://vistaar-docs.mahapocra.gov.in`. Do not change `APP_ORIGIN` to HTTPS
before the certificate exists and `docker-compose.tls.yml` is applied.

## Host Nginx and TLS

Compose no longer runs an Nginx container. It publishes the API, frontend and
Keycloak on **loopback only**, and Nginx installed on the host is the single
entry point:

| Service | Loopback port | `.env` key |
| --- | --- | --- |
| Frontend | 3000 | `UI_HOST_PORT` |
| API | 8002 | `API_HOST_PORT` |
| Keycloak | 8080 | `KEYCLOAK_HOST_PORT` |

The vhost lives at `deploy/nginx-vistaar-docs.conf`. It carries the routing the
application needs: the `/api/` prefix rewrite that matches uvicorn's
`--root-path`, the `/auth/sso-callback` exception where a Next.js route shares
Keycloak's prefix, `client_max_body_size 110m` for PDF uploads, and a 3600s read
timeout so the workspace event stream is not cut every minute.

```bash
sudo apt install -y nginx
sudo cp deploy/nginx-vistaar-docs.conf \
  /etc/nginx/sites-available/vistaar-docs.mahapocra.gov.in.conf
sudo ln -sf /etc/nginx/sites-available/vistaar-docs.mahapocra.gov.in.conf \
  /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

The certificate is the existing `*.mahapocra.gov.in` wildcard, copied from the
edge server to `/etc/ssl/star_mahapocra_gov_in.crt` and `.key` (`644` and `600`,
both `root`). Verify the key belongs to the certificate before reloading:

```bash
sudo openssl x509 -in /etc/ssl/star_mahapocra_gov_in.crt -noout -modulus | md5sum
sudo openssl rsa  -in /etc/ssl/star_mahapocra_gov_in.key  -noout -modulus | md5sum
```

The two sums must match. The wildcard is renewed on the edge server and this
copy does not follow it; re-copy both files and reload Nginx when it is
replaced.

## External Qdrant and embedding service

The bundled Qdrant container is gone. `QDRANT_URL`, `QDRANT_API_KEY`,
`QDRANT_COLLECTION_NAME` and `HF_EMBEDDING_SERVICE_URL` are read from `.env`
and point at existing servers. PostgreSQL, MinIO and Keycloak remain bundled.

`QDRANT_COLLECTION_NAME` is required rather than defaulted. A default silently
sent the deployment at a collection that did not exist on the shared Qdrant,
where search returns nothing and ingestion creates a second empty collection
instead of writing to the intended one. Confirm the name against the server
before deploying:

```bash
curl -s -H "api-key: $QDRANT_API_KEY" "$QDRANT_URL/collections"
```

Changing `APP_ORIGIN` requires `--build`: it is a frontend build argument and
the API validates tokens against `KEYCLOAK_ISSUER`, which derives from it.

The realm import runs only on first startup, so an already-running Keycloak
keeps the old origin. Update the `docs-pipeline-ui` client's redirect URI to
`https://vistaar-docs.mahapocra.gov.in/auth/sso-callback` and its web origin to
`https://vistaar-docs.mahapocra.gov.in` in the admin console, and raise the
realm's SSL requirement from `none`.

`MINIO_CONSOLE_URL` still points at plain HTTP on port 9001, which Compose
publishes on all interfaces. Restrict that port to trusted networks.

## Verify and operate

```bash
docker compose ps -a
docker compose logs --tail=100 db-init api worker keycloak
```

`db-init` should exit with code 0. Other services should be running, with
health checks passing where configured. Login, upload a small PDF, complete
review stages, and test search to verify external AI connections. Startup
health checks do not establish end-to-end ingestion correctness.

```bash
docker compose down
docker compose up -d --build --wait --wait-timeout 300
```

Named volumes retain PostgreSQL data and MinIO objects across ordinary shutdowns.
Qdrant vectors live on the external Qdrant server and are not covered by them.
Do not use `down -v` unless you intend to delete those volumes. Back up both
volumes and the two databases on the existing PostgreSQL server.

The initializer creates missing tables from SQLAlchemy metadata. It does not
migrate an older incompatible schema: the repository currently has no Alembic
revision files. Use fresh dedicated databases for the first deployment or
review the existing schema before startup.

## Remaining server validation

The authoring workspace has no Docker/WSL executable, so image builds, Nginx
configuration validation inside its image, service health checks, login, SSE,
and PDF ingestion must be verified on the deployment server. Confirm the server
IP/domain, PostgreSQL access, AI endpoints, and whether an existing Keycloak
instance should replace the bundled service. The host vhost passed `nginx -t`
against a self-signed certificate at the same paths; the real certificate, the
external Qdrant connection, and the HTTPS login flow remain to be verified on
the server.

Startup ordering follows [Docker Compose dependency conditions](https://docs.docker.com/compose/how-tos/startup-order/).
The Keycloak probe follows its [container health-check guidance](https://www.keycloak.org/observability/health),
and the realm uses [environment placeholders during import](https://www.keycloak.org/server/importExport).

## Local verification results

- Compose YAML, service dependencies, published ports, required environment
  fields, realm placeholders, and Python syntax passed static checks.
- The frontend production build and TypeScript checks passed with Webpack;
  the Dockerfile uses that same build command. Turbopack could not bind its
  helper port in the authoring environment.
- ESLint reports one pre-existing `react-hooks/set-state-in-effect` error at
  `frontend/src/app/login/page.tsx:32` in the remembered-username effect.
- Docker image builds and the running stack remain unverified without Docker.
- Database creation is handled by the local PostgreSQL container; no external
  PostgreSQL server is required.
