# CASCADE SENTINEL

React dashboard and FastAPI service for Pune rainfall and landslide decision support.

## Run the packaged application on Windows

1. Extract the ZIP, preserving the complete `cascade-sentinel` folder structure.
2. Double-click `start.bat`. On its first run it creates a local `.venv` and installs the Python requirements; an internet connection is needed for that installation.
3. The launcher starts the service on **http://127.0.0.1:8000** and opens the browser after the health endpoint responds. Keep the terminal window open while using the app; press `Ctrl+C` there to stop it.

The ZIP includes the compiled React files, so Node.js is not required to run the packaged application.

## Manual startup

From the project directory, use Python 3.10 or newer:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

Then open <http://127.0.0.1:8000>. The runner defaults to `127.0.0.1` and port `8000`; `CASCADE_HOST` and `PORT` can override those defaults when run manually.

## React development

Node.js and npm are only needed when changing the frontend. Install the locked packages and rebuild the assets:

```powershell
npm ci
npm run build
```

The production build is written to `frontend/dist/` and served by FastAPI. During development, `npm run dev` serves Vite on localhost and proxies `/api` to port 8000.

## Checks

```powershell
python -m pytest -q
```

## Scope and safety

The dashboard is decision support, not an official warning or dispatch system. Recommendations do not send public alerts, operate sirens, or authorize evacuations. Live mode is limited to one selected cell; offline demo data is not operational telemetry. Model probabilities and cost/threshold values are assumptions and should be independently checked.

The server binds to localhost by default. Do not expose it to a public or shared network without authentication, authorization, and a security review.
