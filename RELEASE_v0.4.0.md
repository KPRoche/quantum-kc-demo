# Release v0.4.0 — Explicit `tokenStored` on auth-status endpoint

**Release Date:** 2026-05-28
**Status:** 🚧 In progress
**Image:** `ghcr.io/kproche/quantum-kc-demo:v0.4.0`

## Overview

Adds an explicit `tokenStored` field to the `/api/auth/status` response so the
KubeStellar Console doesn't have to infer credential-storage state from
fragile client-side heuristics. Restructures error reporting so transient IBM
upstream blips no longer surface as scary 5xx errors — the response stays 200
with a structured `lastIbmError` payload that classifies the issue.

## Problem fixed

The Console's Quantum Control Panel (PR
[kubestellar/console#15948](https://github.com/kubestellar/console/pull/15948))
shipped a three-state credentials badge — `Configured` / `Stored` / `Not
configured` — but had to infer the `Stored` state with a client-side
workaround:

```ts
const tokenLikelyStored = lastAuthRefresh !== null || authStatus.authenticated
```

This works in the common cases but has known edge cases. The post-merge
review flagged: after a `clear`, `/api/auth/status` returns
`{authenticated: false}` which is still a *successful* fetch, so the
SWR `lastRefresh` updates and the badge falls back to `Stored` instead of
`Not configured`.

The right fix is for the workload to tell the Console the actual storage
state, not for the Console to guess.

## What's new

### 1. `/api/auth/status` response shape

The handler now returns a structured payload that distinguishes "token
saved on the backend" from "token currently validates against IBM":

```json
{
  "tokenStored":   true,
  "authenticated": false,
  "message":       "Credentials saved but not validated this call.",
  "crn":           "crn:v1:bluemix:...",
  "lastIbmError":  null
}
```

`tokenStored` is `true` when **either** of these files exists:

- `/app/credentials/auth.json` — our masked-CRN sidecar (currently on
  emptyDir, lost on pod restart)
- `~/.qiskit/qiskit-ibm.json` — Qiskit's canonical account file (on the
  `qiskit-config` PV, survives pod restart)

Because the Qiskit file lives on a persistent volume, `tokenStored: true`
correctly survives pod restarts even when the emptyDir-backed `auth.json`
is wiped — fixing the original "badge falsely flips to Not configured"
gap.

### 2. Always 200 on the normal path

Pre-v0.4: `/api/auth/status` returned 500 on any exception during validation
— which scooped up genuine credential failures, transient IBM upstream
issues (`max retries attempted`, 5xx, rate-limit), and library-internal
errors into one undifferentiated red banner.

v0.4: the handler returns 200 whenever it successfully determines an
answer, including the `authenticated: false` cases. Failures during
validation flow into `lastIbmError`, which classifies them:

```json
"lastIbmError": {
  "code":      "service_unavailable",
  "message":   "max retries attempted",
  "retryable": true
}
```

`code` ∈ `{rate_limited, service_unavailable, timeout, account_not_found,
unknown}`. `retryable: true` tells the Console to render a soft yellow
"we'll keep retrying" banner; `false` flags a genuine credential problem.

### 3. Narrower 500 path

500 is now reserved for cases where the handler genuinely cannot form an
answer:

- `auth.json` exists but is corrupt / unreadable (JSON parse error,
  permission denied)
- `qiskit_ibm_runtime` is not importable

Everything else — including all IBM upstream weather — stays 200 with a
structured payload.

### 4. Source filename rename

`QuantumKCDemo.v0_3.py` → `QuantumKCDemo.v0_4.py` to match the version bump.
The container build is unaffected — the `Dockerfile` still copies the source
as `qapp.py` inside the image, and `entrypoint.sh` continues to invoke
`qapp.py`.

### 5. New pytest suite

`tests/test_auth_status.py` adds 15 cases covering the response shape:

- 200 paths: no token, valid token, post-restart Qiskit-only file,
  account-drift, transient IBM error, fatal IBM error, classifier keyword
  coverage (parametrized over rate-limit / 503 / timeout patterns).
- 500 paths: corrupt `auth.json`, qiskit-runtime unimportable.

Run locally with:

```bash
pip install -r requirements-dev.txt
pytest tests/
```

The test deps live in a new `requirements-dev.txt` so the production
container image stays lean.

## Console-side follow-up

After this image ships, the KubeStellar Console can drop the
`tokenLikelyStored` inference and key the badge directly off
`authStatus.tokenStored`. That work is tracked separately and depends on
this release being deployed.

## Backward compatibility

The new `tokenStored`, `lastIbmError`, and the always-200 behavior are
additive — older Console clients reading only `authenticated` and `message`
continue to work. The Console's existing fatal-vs-transient classifier
(`classifyApiError`) stays in place during the transition; once the Console
PR lands that consumes `tokenStored` and `lastIbmError`, the client-side
classifier can be retired.
