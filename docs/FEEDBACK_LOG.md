# Nebius / NVIDIA feedback log

Required for the submission. Start at the first live call; record failures as
well as successes. One entry per finding. Never paste API keys.

## Entry template

```markdown
### F<n> — <short title> (YYYY-MM-DD)

- Product / API / model: <Token Factory chat completions | Sandboxes ... >, model ID, SDK/version
- Request: <minimal reproduction; input hashes instead of large payloads>
- Expected:
- Actual: <status code, error text, response excerpt>
- Latency / usage: <ms; prompt/completion tokens; billed units if shown>
- Effect on DocDrift:
- Suggestion:
```

## Questions to answer at the first live probe

- [ ] Nemotron model IDs available to this account; context window.
- [ ] `tools` / `tool_choice` support and tool-call response shape.
- [ ] Usage fields in responses; how credits are drawn.
- [ ] Sandbox: permission, offline execution, image reuse, cancellation timing, artifact download, billed units.

## Entries

None yet: no live call has been made.
