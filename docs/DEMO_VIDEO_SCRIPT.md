# DocDrift demo — website only, about 2:45

**The hosted website is enough for everything shown in this recording.**
Use two tabs in one browser window: the homepage and one completed repair.
The video does not need a terminal, local HTML files, GitHub, or an opened ZIP.
The full spoken text is also in [DEMO_NARRATION.txt](DEMO_NARRATION.txt).

The [official rules](https://nebiusglobalaihackathon.devpost.com/rules) require
a video **under three minutes**, showing the software working, publicly visible
on YouTube, with English materials or an English translation. Submit that video
link, the hosted application URL, and the public repository URL separately in
Devpost. Recording the website does not replace uploading the video or submitting
the form. A face camera is optional.

## Prepare before pressing Record

1. Open [the homepage](https://iljas-vps.tail2832de.ts.net:8443) in tab 1.
   Sign in with the private judge credentials already supplied. Keep the login
   dialog out of the recording. Scroll to the top, where **Repair the example.
   Keep the evidence.** and **Run fresh repair** are visible.
2. Open [this exact completed review](https://iljas-vps.tail2832de.ts.net:8443/jobs/04afd40e6053471d91bd321cd93993dd/review.html)
   in tab 2. Use this link rather than choosing an arbitrary job. Check that the
   heading says **Behavior verified**, the model-call count is **4**, and the
   execution and behavior counts are both **6/6**.
3. In tab 2, click **Logs** in the left sidebar. Scroll to the row labelled
   **final_repaired**, with the case **repeated**, and click its row to expand it.
   This is below the **final_repaired / empty** row. Leave it open, then click
   **Back to top ↑** in the sidebar. Opening it now saves a click while speaking.
4. Keep only those two tabs in the recorded browser window. Return to tab 1.
   During recording, **Ctrl+Tab** switches to the prepared review in tab 2.
   Keep this script on a phone or printed page so it stays out of the footage.
5. In AMD Software, use **1920×1080, landscape, 30 FPS, AVC/H.264, MP4,
   8–10 Mb/s**, and enable the microphone. Start at 100% browser zoom; use 125%
   if the code is too small and the full sidebar still fits. Hide notifications.
   Make a ten-second sample to check voice volume and text readability.

These capture settings are recommendations, not hackathon requirements. At the
suggested bitrate, 2:45 is roughly 170–210 MB including audio. The rules list no
specific resolution, codec, or video-file-size cap; YouTube hosts the upload.
YouTube recommends [MP4/H.264 and 8 Mb/s for 1080p at 30 FPS](https://support.google.com/youtube/answer/1722171?hl=en).

**Leave Run fresh repair untouched for this recording.** The selected review
already contains real Nemotron generation and real Nebius Sandbox verification.
Browsing it and downloading its evidence require no new model call or attempt.
This is a review of a completed run, which the narration explicitly says.

## Record: follow the actions and read only the quoted text

The times are targets, not countdowns. Read naturally, pause for clicks, and aim
to finish around 2:45 so the upload stays under three minutes. Method names
`build` and `positions` are spoken as ordinary words. Say "exit zero" for exit 0.

### 0:00–0:20 — Homepage

**Action:** Start recording in tab 1 at the top of the homepage. Keep the title
and **Run fresh repair** button visible. You can point at the button without
clicking it.

> DocDrift repairs broken Python documentation examples. When a library changes its API, a README can fall behind. NVIDIA Nemotron on Nebius Token Factory proposes a focused fix, and Nebius Sandboxes verify its behavior.

### 0:20–0:35 — Open the prepared review

**Action:** Press **Ctrl+Tab** once. Tab 2 should show **Behavior verified** and
the **6/6** check counts. Stay at the top while saying this paragraph.

> This is a completed real run on our own development fixture. It includes recorded Nemotron generation and actual Sandbox execution, with a behavior-verified result backed by independent checks.

### 0:35–0:55 — Original failure

**Action:** Click **Original failure** in the left sidebar. Keep the original
code and its recorded error visible; scroll a little if necessary.

> The original example calls build, which this demo library does not provide. DocDrift reproduces and records that failure before repairing anything, so we have a concrete baseline for verification.

### 0:55–1:20 — Repair and diff

**Action:** Click **Repair & diff**. Point at `build(words)` on the left and
`positions(words, include_empty=True)` on the right. If **Documentation diff**
is below the screen, scroll down a little to show its red and green lines.

> Here are the original and repaired examples. The agent inspected source, ran a probe, and replaced build with positions. It also preserved empty strings. The diff changes only this Markdown example; source and checks stay protected.

### 1:20–1:40 — Healthy examples

**Action:** Click **Healthy examples**. Show **Required healthy cases: 3**,
**Recorded regression cases: 3**, and **All declared regressions passed: True**.

> This run passed three repaired-input checks and three healthy regression checks. The empty, repeated, and exact-string cases test different behavior. Rechecking healthy examples helps catch a repair that fixes one snippet while breaking another.

### 1:40–2:00 — Model and execution backend

**Action:** Click **Model & usage**. Show the model name, **Inference calls: 4**,
and the token counts while reading the first two sentences. Then click
**Environment** for the last sentence; show **Recorded execution adapter:
nebius_sandbox**.

> The usage section records the Nemotron model, four model calls, and token usage. These are the saved numbers for this repair. The environment section identifies Nebius Sandboxes as the execution backend.

### 2:00–2:25 — Inspect an actual result

**Action:** Click **Logs**, then scroll down about one screen to the already-open
**final_repaired / repeated** row. Stop where its three green **Passed** badges
and **STDOUT** are visible. If the row is closed, click it once to expand it.
The expected stdout is `{"blue": [1], "red": [0, 2]}`.

> This is one of the repaired-input checks. You can inspect its actual output and its separate execution and behavior results. Exit zero alone is insufficient: the frozen expected output and meaningful API-result checks have to pass.

### 2:25–2:45 — Download the evidence and finish

**Action:** Click **Back to top ↑** in the sidebar, then **Download evidence ZIP**
near the page heading. Let the browser download it. Leave the review on screen;
you do not need to open the ZIP or a file manager. Stop recording after the last
sentence.

> The evidence ZIP contains the patch, source snapshots, checks, logs, and usage. Its hashes check file integrity. This MVP covers curated Python examples, and judges can request a fresh repair from the homepage.

## After recording

Watch the recording once. Check that the voice and diff are readable, the
duration is under three minutes, and no login or secret is visible. Upload it to
YouTube with **Public** visibility, then put that URL in the Devpost video field.
Keep the hosted application and public GitHub URLs in their own form fields.

## Provenance for this script

The selected job is the Oct 22 fresh hosted acceptance run (F13),
`04afd40e6053471d91bd321cd93993dd`. Its saved evidence records
`nvidia/nemotron-3-super-120b-a12b`, four model calls, 5,653 prompt tokens,
660 completion tokens (6,313 total), and one exploratory snippet probe. The
tool sequence is `list_files`, `read_file`, `run_python`, `submit_replacement`.
Three repaired-input checks and three healthy regression checks pass with the
`nebius_sandbox` execution adapter; protected file hashes are preserved.

This is an owned development fixture, not an independent upstream bug or a
held-out benchmark. Browsing saved evidence does not mean a new model repair
occurred during filming. Hashes check file integrity, not origin authenticity.
The historical F6 Docker comparison and its later cloud supplement remain
available in the repository; this recording uses the single completed hosted
run instead. The website walkthrough, section links, expanded log, and ZIP
download were rehearsed in a real browser using only read requests.
