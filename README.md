 # Airspace

Airspace is a web application with a Python API backend and a JavaScript frontend. This guide explains how to set up and run both components locally on Windows.

## Functionallity

The application is built to show the most convenient routes for arriving from an airport A to an airport B.

## Requirements

- Python available as `python`, Version 3.12.10 for the backend
- Node.js and npm available as `node` and `npm`, latest version
- Flutter with build configs for Windows, Web and Android
- PowerShell or another terminal

## Backend

Open a terminal in the backend project directory. Create the virtual environment if it does not already exist:

```powershell
python -m venv .venv
```

Activate it in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Then install the Python requirements using:
```powershell
pip install -r requirements.txt
```

Then start the backend server using:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

This runs the ASGI application named `app` in `main.py` with Uvicorn on port `8000`. Leave the terminal running while using the app; press `Ctrl+C` to stop it. The server listens on all network interfaces because of `--host 0.0.0.0`; use this only on a trusted network.

If PowerShell prevents virtual-environment activation, follow your environment's script execution policy or skip activation and run the Uvicorn command above directly. It explicitly uses the virtual environment's Python interpreter.

## Frontend

Open a separate terminal in the frontend directory, where `package.json` is located. Install dependencies and start the development server:

```powershell
npm install
npm run dev
```

Open the local URL printed by the dev server in your browser. Leave the terminal running during development and press `Ctrl+C` to stop the server.

After turning on the ThreeJS server, you need to turn on the Flutter frontend which is the main application entrypoint for the user. Open the `frontend` folder in the Terminal, and then just simply run the `flutter run` command, with build targets for either Windows, Android or Web.

## Running the application

1. Start the backend in one terminal.
2. Start the ThreeJS frontend in another terminal.
3. Start the flutter frontend in another terminal.
3. Visit the flutter local development URL. Backend-dependent features require the API to be running.

If the backend uses FastAPI's default documentation endpoints, interactive API docs are available at `http://localhost:8000/docs` and the OpenAPI schema at `http://localhost:8000/openapi.json`.

## Troubleshooting

- **Command not found:** Install Python or Node.js/npm and ensure the executable is on `PATH`.
- **Port already in use:** Stop the other process using the port or configure the relevant server to use a different port.
- **Missing dependencies:** Install the backend packages using the repository's dependency manifest, and rerun `npm install` in the frontend directory.
