# 40Hero fork: maintenance notes

How 40Hero runs and maintains its fork of Omnigent. Upstream docs cover everything else.

## Branches and remotes

| Remote | Repo | Use |
|---|---|---|
| `origin` | `40Hero/omnigent` | Our fork. Push here. |
| `upstream` | `omnigent-ai/omnigent` | Fetch only. |

- `40hero` is the deploy branch: an upstream point plus our patch stack. Hosts install from it.
- `main` on the fork is not maintained. Compare against `upstream/main`, not `origin/main`.
- As of 2026-11-25, `40hero` was last rebased onto `upstream/main` on 2026-07-10. Upstream is about 5,700 commits ahead since then, so the next rebase will be large.

## Patch stack on `40hero`

List it with `git log --oneline --no-merges $(git merge-base upstream/main origin/40hero)..origin/40hero`.

| Commit | What it does |
|---|---|
| `fix(policies): govern a sub-agent session by its own guardrails` | Upstream builds a sub-agent session's policy engine from the parent's top-level `guardrails`, so a nested worker's own gate never runs and a deny-all parent blocks the child. With the fix, policy resolution descends into `sub_agents`. Without it, a worker that needs different permissions from its parent has to be a top-level agent. |
| `feat(server): OMNIGENT_DEFAULT_AGENTS allowlist` | Comma list of packaged harness seeders to keep (for example `claude,codex`). Unset or empty seeds everything, as upstream does. |
| `fix(claude-native): strip image base64 from resume transcript` | Stops screenshot base64 from being replayed as text on reconnect, which could fill the context window. |
| `fix(claude-native): pin Sonnet 5 custom model option without ucode` | The "Sonnet 5" picker row did nothing on a plain subscription session. This fills in the model id. |
| `feat(acp): grok as a governed-turn harness` + `dynamic CEL gate for grok tool calls` | Grok Build runs through the generic ACP executor. Grok never asks ACP for permission, so a per-session CEL gate checks its tool calls. Fails closed. |

## Rebasing onto upstream

1. `git fetch upstream`. This is always safe.
2. Tag the current head first (for example `40hero-pre-rebase-YYYYMMDD`) and push the tag. It is the rollback point.
3. Rebase `40hero` onto a release tag where you can, or onto `upstream/main`. Check whether DB migrations changed between the two points before you deploy.
4. Conflicts in `_ensure_default_agents` need care: when upstream adds new seeders, fold them into the allowlist tuple. A test that asserts upstream behaviour we changed on purpose (for example image pass-through in `toolUseResult`) is a deliberate change, not a regression. Swap the test case; don't revert the fix.
5. Run `git status` before you call the branch validated. Test fixes you made in the working tree after `rebase --continue` are not in the commit. Amend, then push.
6. After a rebase, a patch whose change upstream already shipped becomes an empty commit and drops out. That's expected.

### Test runs

- Write full output straight to a file: `cmd > out.log 2>&1; echo "EXIT=$?" >> out.log`. Piping through `tail` gives you `tail`'s exit code (always 0) and cuts off the failure.
- Run the suite with `-n auto` (xdist). With the thread method of `pytest-timeout`, a hung test can hang the tests after it.
- The suite has some known noise; it is not a regression from our patches. Tests fail without the optional `databricks` extra. Seccomp, bwrap and real-tmux tests are Linux-only. `test_docker_entrypoint_import.py` and `test_session_host_launch.py` fail under xdist ordering but pass when run alone. To confirm, run the same tests on a worktree of the previous head.

## Web UI changes

The server serves the SPA from `omnigent/server/static/web-ui/`, which is the Vite `build.outDir` and is gitignored. A change under `web/src` goes live only after you rebuild `web/` and restart the server. The commit carries the source only.

## Running it

### agent-server (current)

- Editable install of `/home/trent/workspace/omnigent` (`uv tool install --editable`), so the checkout's branch is what runs. `omni --version` shows the commit from install time and can lag the checkout.
- Two processes, started from wrapper scripts in `~/.omnigent/bin/`: `omnigent-server.sh` (`omni server --host 127.0.0.1 --port 6767`) and `omnigent-host.sh` (`omni host http://127.0.0.1:6767`). No systemd unit; both processes are parented to init.
- The server script sets the database URL and the allowed web origin (`https://agent-server.taile1daab.ts.net`). It holds a credential, so never commit it or copy it into docs.
- Port 6767 is loopback only. Never kill it from another task.

### Mac (as of 2026-07)

- LaunchAgents `com.40hero.omnigent-server` and `com.40hero.omnigent-host` (KeepAlive) run wrapper scripts in `~/.omnigent/bin/`.
- To restart after a code change: `launchctl bootout gui/501/<label>` for host and server, confirm port 6767 is free, check out the branch, reinstall only if deps changed, bootstrap the server, wait for `GET /v1/agents` to return 200, then bootstrap the host and check `GET /v1/hosts`.
- `launchctl bootout` does not kill the server. It detaches and keeps port 6767, so a new server can't bind. Find the real PID with `lsof -nP -iTCP:6767 -sTCP:LISTEN` and kill it.
- Back up `~/.omnigent/chat.db` before a restart that includes migrations.

### Both hosts

- Run one `omni host` per server. Stacked runners cause churn.
- Kill stray processes by Omnigent-specific pattern (`omnigent.runner._entry`, `omnigent.claude_native_bridge serve-mcp`, `omnigent-terminal-`) or by verified PID. Never `pkill -f claude`: it also kills the Claude Code session you are typing in.

## Packaged tiles come back after a restart

Upstream re-seeds every packaged agent on startup, so deleting a row alone doesn't stick. Set `OMNIGENT_DEFAULT_AGENTS` in the server's environment first. If trimmed tiles still come back, delete the builtin rows: in the current schema, `agents.kind` is `1` for template/builtin and `2` for session-scoped, so delete only `kind=1` rows by name. If they keep coming back after that, treat it as a real bug and find the cause in `_ensure_builtin_agent`.

## Decisions

- **Stay on Omnigent, not Hermes Agent (2026-07-06).** Hermes had no working Claude Code delegation and no clean subscription billing. It also had no default approval gate on outbound sends, no policy engine and no persistent spend cap. Re-evaluate if Hermes ships a real `claude` CLI provider, Agent SDK subscription credits, a standalone cron daemon with catch-up, and hardened approval for outbound sends.
- **Keep the metered surface small (2026-06-29).** Anthropic announced that Agent SDK and headless `claude -p` usage would move to a metered credit pool, then paused the change. If it takes effect, `claude-sdk` sessions are on the metered side and `claude-native` sessions are likely on the subscription side. Nobody has confirmed how Omnigent-driven native sessions will be counted. So token-heavy work goes to `claude-native` agents, and agents that need their own gate are top-level agents, not nested ones.

## Still open

- Re-test claude-native sub-agent task delivery (a native worker's terminal starts but never receives the task). Upstream injection fixes landed in the 2026-07-10 range but nobody has re-tested.
- Offer the sub-agent guardrail fix upstream.
