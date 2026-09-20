# Phase 7 admin basics setup

The first Phase 7 slice is read-only and server-enforced. It uses the existing
Google login; no new authentication provider is introduced.

Set `ADMIN_EMAILS` in Vercel to a comma-separated list of Google account emails
allowed to access Story Admin. Add it to Production and the intended Preview
branches, then redeploy. Leave it absent to deny every account by default.

The `/api/admin/content-catalog` endpoint is protected on the server. The UI
does not receive editing or publishing capabilities in this phase.
