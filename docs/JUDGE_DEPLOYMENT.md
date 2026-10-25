# Judge deployment on the current VPS

October 25 state: the user authorized migration from the brother's local
Tailscale profile and completed authentication in their own account. This VPS
is now `iljas-vps`. DocDrift is available at
[its password-protected HTTPS origin](https://iljas-vps.tail2832de.ts.net:8443).
Funnel forwards only HTTPS 8443 to `http://127.0.0.1:8765`; no old-account origin
is reused. Authentication, assets, status, and existing evidence downloads
passed over verified TLS through a public Funnel IP. This was protocol acceptance
from the VPS, not an interactive external-browser session.

The current VPS has room for this small Python service. DocDrift binds only
`127.0.0.1:8765`, uses two dedicated **user** systemd units, and stores its queue
under `.docdrift/judge/`. The web process receives a password digest; only the
worker receives the existing Nebius key. No NewsBias directory, container,
timer, or listener on ports 80, 443, or 8501 is part of this deployment.

These are operator commands for inspection and initial-install reference.
This host is already deployed: preserve its configuration, state, and quota.
Do not repeat activation, the fresh acceptance repair, or the held-out comparison.
Preparation and unit installation are offline; activation consumes the separately
authorized runtime check, and admitted fresh jobs consume service credits.

Deployment state on October 22: the agent now has host access, both dedicated
user services are active and enabled, the startup capability passed, and a fresh
local HTTP repair verified. The four reserved held-out jobs are complete: both
strategies 2/2 verified. Five attempts are used and fifteen remain. Do not repeat
activation or submit another acceptance job to resume this deployment. Public
HTTPS acceptance completed on October 25 using that existing job, with no new
provider calls. See [feedback F13–F15](FEEDBACK_LOG.md) and private
`.docdrift/judge/deployment/public-https-acceptance.json`.

## Check access and the HTTPS route first

GitHub authentication and the agent's workspace permissions are separate. The
earlier agent session had restricted networking and read-only `.git` metadata; a new
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

Host access is working. The checks below inspect the active identity and route;
they should show `iljas-vps` and the existing DocDrift Funnel on 8443.

```bash
tailscale version
tailscale status
tailscale serve status
tailscale funnel status
```

Do not reset Serve/Funnel, restart a shared daemon, or overwrite an existing
route. Preserve the existing DocDrift route on `8443`. During a new installation,
an unrelated mapping on that port must be left alone. Port `10000` is another
supported option if it is unused; update every origin and Funnel command consistently. Leave
port `443` alone. If the daemon is also unavailable in the normal terminal,
the public route is not ready; the Python service can still be inspected locally.

The deployed route uses the user's own Tailscale identity and HTTPS port `8443`.
Funnel requires Tailscale 1.38.3 or newer, MagicDNS, tailnet
HTTPS certificates, and the `funnel` policy attribute. It provides a public HTTPS
address; judges do not need a Tailscale account. Check those requirements in the
[official Funnel guide](https://tailscale.com/docs/features/tailscale-funnel).
This deployment uses the user's own account. On first use, the Funnel command
may print a browser approval link. Tailscale's enablement page provisions HTTPS
and the required Funnel policy attribute; review that page as the tailnet owner.

## Prepare private configuration

Read this machine's full DNS name automatically; the short names in ordinary
`tailscale status` output do not include the tailnet suffix. Run the following
blocks in the same normal VPS terminal, in order. Stop at the first error.
The command checks for a `.ts.net` hostname and prints the exact public origin,
including port `8443`. No hostname needs to be guessed or typed manually.

```bash
cd /home/ubuntu/docdrift/repo
DOCDRIFT_JUDGE_ORIGIN="$(tailscale status --json | .venv/bin/python -c '
import json, sys
name = json.load(sys.stdin)["Self"]["DNSName"].rstrip(".")
if not name.endswith(".ts.net") or "/" in name or ":" in name:
    raise SystemExit("No usable Tailscale DNS name; check MagicDNS in the Tailscale admin console")
print("https://" + name + ":8443")
')"
printf '%s\n' "$DOCDRIFT_JUDGE_ORIGIN"
.venv/bin/python scripts/docdrift_judge_setup.py --prepare \
  --public-origin "$DOCDRIFT_JUDGE_ORIGIN"
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

Use a persistent base Python installation. A virtualenv can remain present
while its interpreter symlink points at a deleted temporary installation; that
caused an actual `203/EXEC` outage on October 23. The installer now refuses a
base interpreter under `/tmp` or `/var/tmp`. This VPS was repaired using:

```bash
uv python install 3.12.13 \
  --install-dir /home/ubuntu/.local/share/docdrift/python --no-bin \
  --cache-dir /home/ubuntu/.cache/docdrift/uv
uv sync --extra dev --locked --link-mode copy \
  --python /home/ubuntu/.local/share/docdrift/python/cpython-3.12.13-linux-aarch64-gnu/bin/python3.12 \
  --cache-dir /home/ubuntu/.cache/docdrift/uv
```

These commands are for this aarch64 VPS. Preserve `.docdrift/` and all external
configuration during environment recovery. Existing virtualenvs keep their old
interpreter references when an installation directory changes; uv documents
the need to recreate them in its [storage reference](https://docs.astral.sh/uv/reference/storage/).
Use `UV_CACHE_DIR=/home/ubuntu/.cache/docdrift/uv` for the test suite and offline
distribution checks as well; the old `/tmp/docdrift-uv-cache` was also absent.

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

The implementation passed all 1,016 offline tests on October 25, including the
systemd 249 `EnvironmentFile=` parsing and persistent-interpreter regression checks.
Rerun the suite if the code or environment changed before startup. If the VPS
user manager cannot apply a hardening setting, inspect its error rather than repeatedly restarting
or removing all protections. This is an operator compatibility issue, not a
reason to touch NewsBias services.

Check that port 8765 has no listener before starting the new service; the `ss`
output should contain only its header. Leave an unrelated listener alone and
resolve the port choice before continuing.

```bash
ss -ltn '( sport = :8765 )'
```

```bash
systemctl --user start docdrift-judge-web.service
curl --fail --retry 5 --retry-connrefused --retry-delay 1 --max-time 3 \
  http://127.0.0.1:8765/healthz
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
.venv/bin/python -m docdrift.judge_service status
```

Wait briefly for the worker heartbeat, then repeat `status` if it initially
reports `worker_unavailable`. Continue only when `live_ready` is true. An HTTP
health response alone does not check the worker or provider capability.

An ambiguous or failed activation keeps its durable receipt; inspect it before
any next step. Never clear `.docdrift/judge/` to retry. The completed F6 state at
`.docdrift/sandbox-f6/` is separate and must also remain intact.

The quota database is also bound by a small state record beside its authorization
file. Preserve both. If the database disappears, startup fails rather than
recreating a fresh twenty-attempt allowance.

## Inspect or publish the DocDrift HTTPS route

The route below is already running persistently in the background. Before a new
publication, inspect Serve/Funnel and confirm the selected port is unused;
preserve an existing matching DocDrift route. The original publication command was:

```bash
tailscale funnel --bg --https=8443 http://127.0.0.1:8765
tailscale funnel status
```

If Tailscale prints an enablement URL, open it in your browser while signed into
the user's own tailnet owner account and follow the HTTPS/Funnel setup there.
Then repeat the same Funnel command. If the local CLI reports permission denied,
run only that Funnel command with `sudo`; do not reset routes or change the
daemon's operator globally. A public DNS update can take a few minutes.

If the enablement page reports `404: node not found`, compare the browser's
selected account/tailnet with the server's active one and confirm that the
admin console lists this VPS. The owner reported this error on October 22;
the server remained online and regenerating its prompt returned the same URL.
The old enrollment was later identified as the brother's; authorized migration
to the user's own account and a new node resolved enablement on October 25.
Do not reuse the old node's link. Tailscale documents switching the
admin console's selected tailnet in its
[multiple-tailnet guide](https://tailscale.com/docs/features/multiple-tailnets).

The public HTTPS origin must exactly match `DOCDRIFT_JUDGE_PUBLIC_ORIGIN`. Funnel
handles TLS and forwards to the loopback web process. The shared password still
protects run creation, run status, and artifact downloads. Do not add a Serve
mapping on that same HTTPS port: [the official Funnel reference](https://tailscale.com/docs/reference/tailscale-cli/funnel)
describes the HTTPS port and reverse-proxy behavior, and the Funnel guide notes
that Serve and Funnel cannot share a port. Never run `tailscale serve reset` or
`tailscale funnel reset` on this shared VPS.

The fresh acceptance repair already completed on October 22. Its job ID is
`04afd40e6053471d91bd321cd93993dd`; its result is `behavior_verified`. For route
checks, inspect that job and download its review/ZIP without creating another
attempt. The October 25 public-network check covered authentication, assets,
status, both saved and acceptance downloads, same-job idempotency, and old-origin
rejection. Its downloaded acceptance ZIP retained SHA-256
`e3cbc421d2bb71f8630bbeb7ba8fd676df7cd87b04a6c831c03dcea2f723394e`.

This host's MagicDNS resolves its own hostname to a private address. Public
acceptance therefore resolved the public Funnel IPv4 through DNS-over-HTTPS
and connected to it with hostname/certificate verification. Ordinary loopback
or private-tailnet access alone would not establish public routing. No interactive
external-browser session is claimed.

Open the origin printed earlier in the browser. The username is `judge`. Read
the generated password only in your private terminal:

```bash
cat ~/.config/docdrift/judge-password.txt
```

Keep that output out of chat and recordings. Log in and inspect the saved or
completed acceptance evidence. Judges may select **Run fresh repair** for a new
attempt; each one counts against the shared allowance, including failures.
Acceptance and the four held-out jobs have used five slots; fifteen remain as
of October 25. The page displays the current allowance.

## Run the approved held-out comparison once

Already completed on this host: one-shot 2/2 verified and agent 2/2 verified.
Do not rerun it or reset its frozen record. The commands below document the
original once-only procedure; `held-out-report` can inspect its saved result.

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

For the development handoff, share only the public origin, `tailscale funnel
status`, the output of `python -m docdrift.judge_service status`, the acceptance
job ID/verdict, and any error with credentials removed. The password, provider
key, full Tailscale JSON, and private environment files are not needed.

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
