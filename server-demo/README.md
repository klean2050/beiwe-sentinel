# Sentinel server demo

Runs the unmodified [onnela-lab/beiwe-backend](https://github.com/onnela-lab/beiwe-backend) on one machine, loads the Sentinel pilot study, and fills it with about two weeks of synthetic data from four simulated phones. Use it to explore the researcher website before deploying to AWS. It is a local demo, not a production setup.

What it exercises, all through the backend's own code:

- Study import (`copy_study_from_json`) with the Sentinel surveys, schedules, app settings, a baseline-visit date and Site/Cohort fields
- Participant creation with encryption keys
- Phone registration (`/register_user`) and encrypted uploads (`/upload`), using the apps' file encryption: GPS, accelerometer, screen events, call and text logs on Android, and survey answers and timings
- File processing into hourly chunks, and Forest Jasmine, Willow and Sycamore tasks

## One-time setup (Linux or macOS)

1. Install PostgreSQL and create a local server where the `beiwe` user can connect from `127.0.0.1` without a password (local trust authentication).
2. Clone the backend and install it with Python 3.12:
   ```bash
   git clone https://github.com/onnela-lab/beiwe-backend.git
   ```
   ```bash
   cd beiwe-backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt "moto[server]"
   ```
   `moto` provides a local stand-in for S3.
3. Copy `env.example.sh` to `env.sh` in this folder.

## Run

```bash
BACKEND_DIR=/path/to/beiwe-backend ./rebuild.sh
```

This wipes the local demo database, rebuilds everything in about ten minutes, and leaves the website at http://localhost:8080. Log in as `sentinel_admin` with password `Sentinel-Demo-Admin-2026!`. Site administrators need passwords of at least 20 characters.

## Files

| File | Purpose |
|---|---|
| `sentinel_study.json` | The Sentinel study in Beiwe's export format, from `prototype/index.html` plus a two-week follow-up survey |
| `seed.py` | Creates researchers, the study and six participants |
| `phone_sim.py` | Registers four simulated phones and uploads encrypted data |
| `run_forest.py` | Runs the Forest tasks and prints a sample of the results |
| `rebuild.sh` | Runs everything in order |

## Known quirks

- The participant table's column labels shift by one until Firebase credentials are uploaded. Its header leaves out the baseline-date column without Firebase, but the data still includes it.
- The researcher pages load jQuery, Angular and Bootstrap from public CDNs, so the browser needs internet access.
- With 90 seconds of GPS every 15 minutes, Jasmine reports more than 24 hours at home on days spent entirely at home. Check this with the Onnela lab before using home time as an outcome.
