Local Keycloak imports
======================

The local stack imports `docs-pipeline-realm.json` on first boot.

It creates only:

  /global/super-admin

mapped to the single application role:

  super_admin

It also creates the local client names used by the app:

  docs-pipeline-api
  docs-pipeline-ui

If the `keycloak-data` volume already exists, Keycloak will not re-import the
realm. Recreate that volume when you want a clean local Keycloak state.
