# Review report — grok-acp-gate

Read-only risk review over the branch diff (`grok-acp-gate` vs `40hero`), two independent lanes: codex (cross-vendor, correctness/security) + a frontier adversarial reviewer. All confirmed findings verified against the code; fixes applied and re-tested.

## Summary

- **Tier:** deep (external egress-gate surface)
- **Ship blockers:** 0 remaining (7 confirmed, all fixed or mitigated; 2 residuals documented + owed)
- **Total confirmed:** 7 (+ 2 residual risks)

## Findings

Severity-ranked; every confirmed finding was fixed unless marked residual.

- **[high] fail-open-under-sandbox `omnigent/grok_acp_gate.py`** — grok's PreToolUse hook is fail-OPEN if it cannot spawn; under an active OS sandbox the hook interpreter may be outside the read roots, so the gate silently disappears exactly in the confine-untrusted-agent case. Failure scenario: grok launched with `os_env.sandbox != none`, hook fails to exec, tool runs ungated. **Fixed (guard) + residual:** the executor now REFUSES to run grok under an active sandbox rather than run open; the self-contained hook removes the omnigent-package dependency. Residual owed: extend sandbox read roots to cover the interpreter + GROK_HOME so sandboxed grok can run gated. Confirmed.
- **[high] hook-shadow / -m cwd resolution `omnigent/grok_acp_gate.py:100`** — `python -m omnigent.grok_acp_hook` resolves modules via cwd, so a malicious repo could ship `omnigent/grok_acp_hook.py` printing allow. Failure scenario: grok run in an untrusted repo whose cwd shadows the module. **Fixed:** a self-contained stdlib hook is copied into GROK_HOME and invoked by absolute path (no `-m`, no omnigent import). Confirmed.
- **[high] truncated-input bypass `omnigent/grok_acp_gate.py`** — grok's envelope carries `toolInputTruncated`; the mapper ignored it, so policy could judge a benign prefix while grok executes the full input. Failure scenario: oversized shell arg, benign head, malicious tail. **Fixed:** the gate denies when `toolInputTruncated` is set, before the decider runs. Confirmed.
- **[high] _decide_permission fails open `omnigent/inner/acp_executor.py`** — a policy-eval exception became `action=None` and fell through to elicitation/allow; no-bridge returned True. Failure scenario: policy backend errors on what would be a DENY, tool runs. **Fixed:** grok-scoped `strict=True` mode denies on policy exception and on a missing verdict/bridge; explicit ALLOW still allows; generic ACP agents keep the lenient default. Confirmed.
- **[med] grok detection bypass `omnigent/inner/acp_executor.py`** — `basename(argv[0]) == "grok"` missed `env grok` / `grok.exe` / wrappers, silently losing the gate. **Fixed:** detection scans all argv tokens for a `grok`/`grok.exe` binary. Confirmed.
- **[med] credential temp-dir leak `omnigent/grok_acp_gate.py`** — if `start()` raised after `mkdtemp` but before `self._home` was set, the dir holding a copy of the real `auth.json` was never cleaned. **Fixed:** `self._home` is assigned immediately after `mkdtemp`, so every failure path is cleanable. Confirmed.
- **[med] unbounded stdin fail-open `omnigent/grok_acp_hook.py`** — every network path had a 30s timeout, but `stdin.read()` had none; a stuck stdin could outlive grok's 60s kill with no deny emitted. **Fixed:** a SIGALRM wall-deadline (40s < grok's 60s) denies. Confirmed.
- **[low] no auth on /evaluate `omnigent/grok_acp_gate.py`** — the loopback bound 127.0.0.1 (not remotely reachable) but any local process could POST and drive the policy / fish for a consent prompt. **Fixed:** a per-session token (set in the hook env) is required on `/evaluate`; untokened requests deny without running the decider. Confirmed.

## Coverage manifest

| Risk class | Status | Note |
|---|---|---|
| Correctness | checked | codex + frontier; ALLOW strict-mode regression caught by the e2e and fixed |
| Security / auth | checked | egress gate is the whole surface; fail-open paths closed, endpoint tokened |
| Fail-open / fail-closed | checked | both lanes confirmed the 30s<60s<120s timeout chain fails closed; stdin gap closed |
| Injection / bypass | checked | hook-shadow, truncated-input, argv-detection bypasses all fixed |
| Secrets handling | checked | credential temp-dir leak on error paths fixed; dir is 0700 |
| Concurrency / races | checked | teardown-vs-handler race fails closed; restart guarded (no gate leak) |
| Sandbox interaction | unavailable (residual) | refuse-under-sandbox guard added; read-root coverage for the hook interpreter is OWED |
| Subagent tool coverage | not-checked (residual) | whether grok's ≤8 subagents' internal tool calls fire the parent PreToolUse hook is UNVERIFIED — the key owed verification before trusting grok for autonomous subagent work; conservative mitigation = policy-deny `spawn_subagent` for gated grok |

Cross-vendor lane: codex ran (147k tokens, 4 high findings). Frontier adversarial lane ran (5 findings + confirmed-clean list). No lane unavailable.
