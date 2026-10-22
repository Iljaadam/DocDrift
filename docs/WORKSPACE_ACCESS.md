# Restore Git and network access for this workspace

Host access was restored on October 22. DNS, GitHub SSH, systemd, and Tailscale
checks now succeed, and the agent has performed local activation and live
verification. The original checkout is synchronized with the pushed prepared
commits and can use Git normally. The instructions below are troubleshooting history for a future
restricted session; they are not additional steps for the current deployment.

## Let the agent perform the deployment

The owner asked on October 22 for the agent to run deployment rather than hand
over a long command list. Resuming the current chat reported that it was already
open in another app. The installed CLI supports creating a new conversation
with its recorded history; run this in the normal VPS terminal and choose the
DocDrift conversation in the fork picker:

```bash
codex fork --no-daemon -C /home/ubuntu/docdrift/repo --sandbox danger-full-access --ask-for-approval on-request
```

This requests local host access while retaining on-request approvals, allowing
the agent to use the user service manager, Tailscale, Git, and authorized Nebius
requests. Forking preserves the original chat and avoids requesting ownership
of that same conversation. The reported error may mean the current app still
holds it even while idle; no stale lock or orphan process has been established.
No lock deletion or daemon restart is needed for this handoff. Say "proceed with
the hosted judge deployment; read AGENTS.md and STATUS.md first" in the new chat.
It does not change the already-running restricted executor. A managed
host policy may reject or override the requested mode; that requires the host
owner's environment settings rather than another shell workaround. D31's quota,
credit-only intent, and NewsBias exclusions continue to apply. See the official
[agent approvals documentation](https://learn.chatgpt.com/docs/agent-approvals-security).
The official [CLI reference](https://learn.chatgpt.com/docs/cli/reference)
documents `codex fork` as a new chat preserving the original transcript.

The narrower profile below is an alternative where the host supports explicit
filesystem, network, and local service-access controls.

The VPS has `gh`, Git, and Tailscale installed. This agent's executor has a
separate managed filesystem/network policy: `.git` is read-only and outbound
command networking is restricted. A working GitHub login does not change that
policy. Ordinary `workspace-write` also protects Git metadata by default; see
the official [agent approvals documentation](https://learn.chatgpt.com/docs/agent-approvals-security).

## Normal-terminal checks

```bash
cd /home/ubuntu/docdrift/repo
getent hosts github.com
gh auth status -h github.com
git ls-remote origin HEAD
```

If DNS works and `gh` actually rejects its saved credentials, run
`gh auth refresh -h github.com`, or `gh auth login -h github.com` if no account
exists. The repository uses SSH, so its Git authentication is separate from
`gh`; do not change the remote merely because the CLI check fails. Never print
tokens to diagnose either path.

## Select a compatible permission profile in a new session

If your Codex installation supports named permission profiles, merge this
example into its user configuration, preserving existing tables. The profile
adds access only for DocDrift's Git metadata and its required API hosts. Select
`docdrift` in the environment's permissions configuration and restart/resume the
workspace with that profile. Configuration changes cannot alter this already
running sandbox.

```toml
[features]
network_proxy = true

[permissions.docdrift]
extends = ":workspace"
description = "DocDrift editing, Git delivery, and approved Nebius requests."

[permissions.docdrift.filesystem]
"/home/ubuntu/docdrift/repo/.git" = "write"

[permissions.docdrift.network]
enabled = true

[permissions.docdrift.network.domains]
"github.com" = "allow"
"api.github.com" = "allow"
"ssh.github.com" = "allow"
"api.tokenfactory.nebius.com" = "allow"
"127.0.0.1" = "allow"
```

The official [permission-profile reference](https://learn.chatgpt.com/docs/permissions)
documents inheritance, explicit path overrides, and network filtering. Managed
policy may restrict available profiles or forbid an override; the environment
owner must enable it in that case. Keep other protected paths protected.
SSH and local daemon sockets may still require separate host support; this
example does not grant access to Docker or Tailscale sockets or change a route.

For older Codex CLI installations, network access can instead be enabled with
`sandbox_workspace_write.network_access = true`, and eligible command approvals
with an on-request approval policy. That alone does not make protected Git
metadata writable. Use the host's permitted approval/profile controls or the
normal-terminal delivery workflow; do not change ownership or use world-writable
permissions.

After a new session starts, check its effective permissions and ask it to
verify access. Git/network commands should be tested before service activation.
Use [the VPS deployment guide](JUDGE_DEPLOYMENT.md) for the separate judge units,
private credentials, and HTTPS route. Neither a permission change nor GitHub
authentication authorizes additional provider activity beyond D31's quota.

## Previous restricted-session Git delivery

The earlier restricted executor prepared commits in an isolated writable
checkout. On October 22 the agent pushed them, verified all 211 original
worktree files against that commit, and fast-forwarded the original checkout's
metadata without changing worktree bytes or private state. Future delivery can
use this repository directly:

```bash
git -C /home/ubuntu/docdrift/repo push origin main
```

The old isolated checkout at `/tmp/docdrift-delivery-ctctogzg/repo` and full-history
bundle at `.docdrift/access/docdrift-main.bundle` remain backups. The private
delivery receipt records the latest pushed commit. Preserve private run state;
there is no remaining original-worktree mismatch to repair.
