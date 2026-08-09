# Loudmouth — clean-machine smoke test checklist

Run before every external release, on a Windows machine (or VM) **with no
Python installed** — Pegasus via tailnet is the standard rig. This is the
manual half of "done done": a consumer downloads one file, installs it,
reboots, and `/health` answers.

## Install

- [ ] Download `LoudmouthSetup-<version>.exe` from the GitHub Release (or `idealoom.ai/download/loudmouth` once the redirect is live)
- [ ] SHA-256 of the download matches `SHA256SUMS.txt`
- [ ] (Signed builds) Properties → Digital Signatures shows the Stark Technologies signature, timestamped
- [ ] Note any SmartScreen interstitial — expected until publisher reputation accumulates; record wording/screenshot
- [ ] Installer runs to completion; no console window appears at any point
- [ ] Files landed in `%ProgramFiles%\Stark\Loudmouth`
- [ ] Task Scheduler shows the "Loudmouth Audio Server" logon task for the installing user

## Immediately after install (no reboot)

- [ ] `http://127.0.0.1:8765/health` returns `{"status":"ok", ...}` with correct `version`, `protocol: 1`, `port: 8765`
- [ ] `POST /play` with `{"file": "loudmouth-test.mp3"}` plays the full test sentence — no clipped first word
- [ ] `GET /status` and `POST /stop` behave
- [ ] Log file exists at `%LOCALAPPDATA%\Loudmouth\loudmouth.log`

## After reboot + logon

- [ ] Loudmouth is running (no manual start), `/health` answers, `uptime` is small
- [ ] Still no visible window

## Port policy

- [ ] Occupy 8765 with another process, restart Loudmouth → binds 8766, `/health` on 8766 reports `port: 8766`
- [ ] Occupy both → process exits; log states both ports were in use

## Browser detection (per browser: Chrome, Edge, Firefox)

- [ ] From the allowlisted test origin (tailnet path `http://100.64.58.91:8910` or `https://idealoom.ai`): fetch of `/health` succeeds
- [ ] Chrome 142+: LNA permission prompt appears once; after allow, detection works; after deny, failure mode noted
- [ ] Firefox: no prompt; request succeeds (record any differences)
- [ ] From a non-allowlisted origin (e.g. a page on `http://localhost:9999`): browser blocks the response (no CORS headers)

## Regression

- [ ] Existing ConfRoom consumer plays audio unchanged against the new build (point it at the new port)

## Uninstall

- [ ] Settings → Apps → Loudmouth → Uninstall completes
- [ ] Scheduled task gone; `%ProgramFiles%\Stark\Loudmouth` gone; `%LOCALAPPDATA%\Loudmouth` gone
- [ ] `loudmouth.exe` process not running

## Pre-announce

- [ ] Multi-engine AV scan (e.g. VirusTotal) of BOTH `loudmouth.exe` and `LoudmouthSetup-<version>.exe`; record detections
