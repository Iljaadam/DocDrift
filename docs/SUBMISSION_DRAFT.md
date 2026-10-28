# DocDrift — submission draft

- **Track:** Coding and Agentic Engineering
- **Code:** https://github.com/Iljaadam/DocDrift
- **Demo:** https://iljas-vps.tail2832de.ts.net:8443
- **Video:** add the public YouTube URL after recording.

## Tagline

DocDrift uses NVIDIA Nemotron on Nebius Token Factory to repair broken Python documentation examples, verifies fixes in Nebius Sandboxes, and exports a reviewable patch with execution evidence.

## Built with

Priority tags: Python, JavaScript, HTML5, CSS3, NVIDIA Nemotron, Nebius Token
Factory, Nebius Sandboxes, Docker, SQLite, HTTPX, markdown-it-py, pytest, uv,
Git, GitHub, Tailscale.

Additional build/deployment tags: Linux, Ubuntu, systemd, Hatchling.

These twenty options describe the implemented stack. Choose matching labels
in the form; the twenty-five-tag limit is a maximum. The service uses Python's
standard HTTP server and a custom agent loop.

## Project story

Copy the [seven-section Markdown story](SUBMISSION_STORY.md) into Devpost's
Project Story field.

## Testing instructions

Open the hosted demo and sign in as `judge` with the passphrase provided in the
private testing instructions. Select **Run fresh repair**, then inspect its
review and evidence ZIP. No provider account, API key, Tailscale account, or local
installation is needed. The app shows the remaining shared attempt allowance.

The [judge quickstart](JUDGE_QUICKSTART.md) also offers saved evidence and a free
manual Docker verification route. Maintain hosted access through December 15.
Before submission, resolve whether the fixed shared allowance satisfies the
rules' unrestricted testing requirement and confirm granted-credit funding;
Sandbox billing coverage remains unverified.

## Nebius / NVIDIA feedback

Nemotron's standard tool calls supported the source-reading and execution loop.
A concrete improvement would be clearer Sandbox image-import errors and an
explicit statement of promotional-credit coverage for Sandbox execution and
storage. The [feedback log](FEEDBACK_LOG.md) includes successful calls, failures,
usage accounting, and reproduction details.
