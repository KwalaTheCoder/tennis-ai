# Tennis AI — Didban Tennis

A local-first tennis analytics dashboard for pre-match and live probability estimates, fair-odds comparison, prediction tracking, and model evaluation.

## Highlights

- Pre-match and live match analysis
- Surface-aware Elo ratings
- Transparent probability baseline
- Fair-odds comparison
- Non-duplicating prediction snapshots
- Result settlement and evaluation with Brier score, log loss, and accuracy
- Local SQLite history
- Optional Live Tennis API connection

## Run locally

Requires Python 3.10+ and uses only the Python standard library.

```powershell
.\start.ps1
```

Open `http://127.0.0.1:8775`.

The dashboard also supports manual mode when no provider key is configured.

## Configure live data

Run the interactive setup script:

```powershell
.\configure-key.ps1
```

The key is stored as the Windows user environment variable `LIVE_TENNIS_API_KEY`; it is not written into the repository.

## Tests

```powershell
python test_server.py
```

## Project structure

- `server.py` — local HTTP API, analytics model, provider integration, and SQLite persistence
- `index.html`, `styles.css`, `app.js` — Persian dashboard interface
- `test_server.py` — automated model and API tests
- `start.ps1` — local launcher

## Responsible use

This project provides experimental probability estimates, not guaranteed outcomes or financial advice. Real performance requires sufficient historical evaluation, calibration, and independent validation.
