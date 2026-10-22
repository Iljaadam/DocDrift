# Judge deployment on the current VPS

The current VPS has room for this small Python service. DocDrift binds only
`127.0.0.1:8765`, uses two dedicated **user** systemd units, and stores its queue
under `.docdrift/judge/`. The web process receives a password digest; only the
worker receives the existing Nebius key. No NewsBias directory, container,
timer, or listener on ports 80, 443, or 8501 is part of this deployment.

These are operator commands for the normal VPS terminal. Preparing configuration
and installing units are offline. Activation makes the separately authorized
runtime check; starting the worker permits admitted jobs to consume credits.
The service is not deployed merely because these files exist.

## Check access and the HTTPS route first

GitHub authentication and the agent's workspace permissions are separate. This
agent session has restricted networking and read-only `.git` metadata; a new
`gh` login cannot change either. Relaunch the agent session with outbound
network access and write access to this repository's `.git` in its environment
permissions, if those controls are available. Otherwise, run the small operator
steps here in the normal terminal; do not change repository ownership or make
`.git` world-writable.
The exact profile example and checks are in [workspace access](WORKSPACE_ACCESS.md).

```bash
cd /home/ubuntu/docdrift/repo
getent hosts github.com
gh auth status -h github.com
git ls-remote origin HEAD
```

The remote uses SSH (`git@github.com:Iljaadam/DocDrift.git`), so `git ls-remote`
tests a different credential path from the GitHub CLI. If normal-terminal DNS
works but `gh auth status` reports an actual authentication error, refresh its
stored credentials with `gh auth refresh -h github.com`, then repeat the check.
If no account is configured, use `gh auth login -h github.com`. Do not use
`--show-token` or paste credential output into chat. An SSH authentication error
needs the VPS's GitHub SSH key checked; refreshing `gh` alone will not fix it.
These commands follow the [GitHub CLI status](https://cli.github.com/manual/gh_auth_status)
and [refresh](https://cli.github.com/manual/gh_auth_refresh) documentation.

Tailscale is installed, but this restricted agent session could not connect to
the local `tailscaled` daemon on October 22. Existing route configuration and
Funnel eligibility are therefore **unverified**. Check from the normal terminal:

```bash
tailscale version
tailscale status
tailscale serve status
tailscale funnel status
```

Do not reset Serve/Funnel, restart a shared daemon, or overwrite an existing
route. If `8443` already has a Serve or Funnel route, leave it alone and review
the route choice before continuing. Port `10000` is another supported option
if it is unused; update every origin and Funnel command consistently. Leave
port `443` alone. If the daemon is also unavailable in the normal terminal,
the public route is not ready; the Python service can still be inspected locally.

The recommended route uses the VPS's existing Tailscale identity and an unused
HTTPS port `8443`. Funnel requires Tailscale 1.38.3 or newer, MagicDNS, tailnet
HTTPS certificates, and the `funnel` policy attribute. It provides a public HTTPS
address; judges do not need a Tailscale account. Check those requirements in the
[official Funnel guide](https://tailscale.com/docs/features/tailscale-funnel).
This plan assumes no newly created third-party account and changes no tailnet
policy automatically.

## Prepare private configuration

Use the DNS name shown for this VPS in Tailscale, for example
`https://YOUR-VPS.YOUR-TAILNET.ts.net:8443`. This must be the exact origin judges
will open, including the port. Do not put a passphrase in the URL.

```bash
.venv/bin/python scripts/docdrift_judge_setup.py --prepare \
  --public-origin https://YOUR-VPS.YOUR-TAILNET.ts.net:8443
.venv/bin/python -m docdrift.judge_service prepare \
  --state-root .docdrift/judge \
  --authorization .docdrift/access/judge-authorization-2026-10-22.json
```

The helper creates the following files with mode `600`, without printing their
contents:

- `~/.config/docdrift/judge-password.txt`: the generated shared passphrase.
- `~/.config/docdrift/judge.env`: its SHA-256 digest and the exact public origin.

The existing `~/.config/docdrift/nebius.env` is reused in place; the helper never
reads or copies its contents. Existing secrets and differing unit files are
never overwritten. Repeating `--prepare` with the same origin keeps the same
password. To change the origin later, stop the web unit and deliberately edit
only `DOCDRIFT_JUDGE_PUBLIC_ORIGIN` in the private `judge.env`; preserve the digest
and mode `600`. Then repeat preparation with the new origin to check consistency.
The explicit origin `http://127.0.0.1:8765` is accepted for a local inspection;
replace it with the real HTTPS origin before exposing the service.

Read the passphrase only in your private terminal when supplying the testing
instructions to judges. Never add it to Git, the submission's public description,
a recording, an evidence archive, or chat.

The authorization record at
`.docdrift/access/judge-authorization-2026-10-22.json` is a separate local record
of the user-approved allowance. On October 22 the owner approved the twenty
bounded attempts and proceeding while they check usage, with the stated intent
to use only granted credits. That instruction authorizes this scoped deployment;
it does not establish Sandbox credit coverage or a guaranteed dollar ceiling.
The reported $30.98 balance is specifically Token Factory credit. Consult
[the hosting plan](JUDGE_HOSTING_PLAN.md) for the complete allowance. The older
F6 authorization is consumed and does not authorize these new jobs.

## Install and inspect the units

```bash
.venv/bin/python scripts/docdrift_judge_setup.py --install
systemd-analyze --user verify \
  ~/.config/systemd/user/docdrift-judge-web.service \
  ~/.config/systemd/user/docdrift-judge-worker.service
```

Installation creates units and runs `systemctl --user daemon-reload`; it does
not enable or start them. The templates use the repository's absolute virtualenv
Python and working directory. The web unit has a 25% CPU quota; the worker has
50%. Each has a 384 MiB memory limit, 32-task limit, lower scheduling priority,
and a read-only filesystem except its private state directory and temporary
files. The web unit strips provider keys from its environment and hides the
Nebius env file and plaintext passphrase. The worker's key is loaded by the
systemd manager before its filesystem restrictions apply.

Run the project's offline tests before startup. If the VPS user manager cannot
apply a hardening setting, inspect its error rather than repeatedly restarting
or removing all protections. This is an operator compatibility issue, not a
reason to touch NewsBias services.

```bash
.venv/bin/python -m pytest -o addopts=""
systemctl --user start docdrift-judge-web.service
curl --fail --max-time 5 http://127.0.0.1:8765/healthz
```

At this point the loopback interface may show saved evidence and an inactive
fresh-run button. Do not infer live readiness from an HTTP health response.
Inspect the authorization and activation state with:

```bash
.venv/bin/python -m docdrift.judge_service status \
  --state-root .docdrift/judge \
  --authorization .docdrift/access/judge-authorization-2026-10-22.json
```

After the offline checks pass, activate once in the normal terminal with the
existing key loaded. This consumes the one reserved capability operation under
the October 22 authorization:

```bash
set -a
. ~/.config/docdrift/nebius.env
set +a
.venv/bin/python -m docdrift.judge_service activate \
  --state-root .docdrift/judge \
  --authorization .docdrift/access/judge-authorization-2026-10-22.json --live
systemctl --user start docdrift-judge-worker.service
```

An ambiguous or failed activation keeps its durable receipt; inspect it before
any next step. Never clear `.docdrift/judge/` to retry. The completed F6 state at
`.docdrift/sandbox-f6/` is separate and must also remain intact.

The quota database is also bound by a small state record beside its authorization
file. Preserve both. If the database disappears, startup fails rather than
recreating a fresh twenty-attempt allowance.

## Publish only the unused HTTPS route

Immediately before publishing, repeat `tailscale serve status` and
`tailscale funnel status` to confirm `8443` is still unused. Then:

```bash
tailscale funnel --bg --https=8443 http://127.0.0.1:8765
tailscale funnel status
```

The public HTTPS origin must exactly match `DOCDRIFT_JUDGE_PUBLIC_ORIGIN`. Funnel
handles TLS and forwards to the loopback web process. The shared password still
protects run creation, run status, and artifact downloads. Do not add a Serve
mapping on that same HTTPS port: [the official Funnel reference](https://tailscale.com/docs/reference/tailscale-cli/funnel)
describes the HTTPS port and reverse-proxy behavior, and the Funnel guide notes
that Serve and Funnel cannot share a port. Never run `tailscale serve reset` or
`tailscale funnel reset` on this shared VPS.

Check from a device outside the tailnet: login, read the fixture description,
run one fresh attempt, wait for a terminal result, and download its sanitized
review and archive. That acceptance attempt counts toward the twenty approved
attempts; it is not an extra free test. Preserve four attempts for the separately
approved held-out comparison. A saved F6 page is not proof that the fresh path
works.

## Run the approved held-out comparison once

After code and offline checks are frozen and the worker is active, queue the
four reserved jobs: the two untouched held-out fixtures, each under one-shot
and agent strategies. This consumes four of the twenty attempts. Repeating the
command returns the same jobs rather than submitting a second comparison.

```bash
.venv/bin/python -m docdrift.judge_service held-out --live
.venv/bin/python -m docdrift.judge_service held-out-report
```

The report command is offline and can be repeated while work is pending; its
status stays `incomplete` until all four actual jobs finish with live evidence.
It writes `.docdrift/judge/held-out-comparison.json`, including failed outcomes
and usage. A controller change between queued held-out jobs stops them; inspect
the frozen record rather than rerunning cases after an implementation change.
No held-out score exists merely because the queue or report command succeeds.

Only after the acceptance result is reviewed:

```bash
systemctl --user enable docdrift-judge-web.service docdrift-judge-worker.service
loginctl show-user "$USER" -p Linger
```

If `Linger=no`, a user manager may stop after logout. For this login only, the
operator can enable persistence with `sudo loginctl enable-linger "$USER"`.
This is a system setting for the current user; no NewsBias unit is enabled,
disabled, restarted, or otherwise changed. The app stops new admissions after
December 15; maintain its saved artifacts for the judging period.

## Operations and rollback

```bash
systemctl --user status docdrift-judge-web.service docdrift-judge-worker.service
journalctl --user -u docdrift-judge-web.service -u docdrift-judge-worker.service -n 60 --no-pager
```

Review journal output privately before sharing it. Do not dump the process
environment, private authorization records, provider response files, or the
plaintext password to debug the service. Compare Token Factory usage in its
dashboard and Sandbox usage with official billing records. Sandbox resource
`cost` fields have unconfirmed units and do not establish a billed dollar amount.

To pause the demo, stop only these units:

```bash
systemctl --user stop docdrift-judge-web.service docdrift-judge-worker.service
```

Once a worker is interrupted, inspect saved status before restarting; uncertain
submissions remain counted. A worker exception or interrupted active job pauses
new admissions and execution of queued jobs, because a previously accepted
operation may still be in flight. A restart does not clear that pause. Reconcile
the saved operation IDs and any uncertain model call before arranging a reviewed
recovery; do not edit quota rows, reset the database, or resubmit the old job.
To remove the public DocDrift route, and only if
`8443` is still the route created above:

```bash
tailscale funnel --https=8443 off
systemctl --user disable docdrift-judge-web.service docdrift-judge-worker.service
```

Keep the state, receipts, secrets, and completed-run downloads. Stopping a
service or removing the route does not delete provider-side data or establish
its retention behavior.
