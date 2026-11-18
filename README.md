# NAO Smart Classroom Monitoring System

## Online frontend

Open the GitHub Pages website:

https://bostonlee05.github.io/fyp_nao/

GitHub Pages hosts only the frontend. Flask, YOLO, InsightFace, the
NAO camera, and the NAO robot connection must run on a laptop that is
connected to the NAO.

## What you can test away from the lab

- Static page navigation
- GitHub Pages deployment
- The frontend-to-backend connection screen
- Supabase database migration, once PostgreSQL support is added

You cannot test face registration, face recognition, the NAO camera,
attendance recording, or robot speech until the NAO and laptop are
available.

## Requirements on the lab laptop

Install Python and the project dependencies:

```powershell
py -m pip install flask flask-cors ultralytics insightface deep-sort-realtime
py -m pip install qibullet libqi-windows numpy opencv-python
py -m pip install pyttsx3 pillow python-dotenv google-genai requests
py -m pip install silero-vad torch faster-whisper
```

Install Cloudflare Tunnel:

```powershell
winget install Cloudflare.cloudflared
```

NAOqi may require the project to use the Python version specified for
the lab environment. The NAO IP is configured in `src/config.py`.

## Start the application

Open PowerShell in the repository root:

```powershell
cd C:\path\to\fyp_nao
py src\main.py
```

Flask normally listens on:

```text
http://localhost:5000
```

Keep this terminal open.

## Create the public tunnel

Open a second PowerShell terminal:

```powershell
cloudflared tunnel --url http://localhost:5000
```

Copy the HTTPS URL printed by Cloudflare. It will look similar to:

```text
https://random-name.trycloudflare.com
```

Keep both terminals open. Do not close Cloudflare or Flask during the
demonstration.

## Connect the GitHub Pages website

1. Open https://bostonlee05.github.io/fyp_nao/.
2. Enter the HTTPS Cloudflare Tunnel URL when prompted.
3. Select **Save and Connect**.
4. Open **Settings** if the tunnel URL needs to be changed later.

The tunnel URL is saved in the browser's local storage. Each demonstration
browser may need to enter it once. A quick-tunnel URL normally changes
after Cloudflare or the laptop restarts.

## Teacher demonstration checklist

1. Switch on the NAO and connect it to the laptop network.
2. Connect the lab laptop to the NAO IP.
3. Start Flask.
4. Start Cloudflare Tunnel.
5. Open the GitHub Pages website.
6. Enter the current tunnel URL.
7. Register one or more students and their face data.
8. Open **Vision Monitoring** and start Vision.
9. Start an attendance session.
10. Test face recognition and attendance live.

## Troubleshooting

### The website cannot reach Flask

- Confirm Flask is still running.
- Confirm the Cloudflare terminal is still running.
- Copy the newest HTTPS tunnel URL into the Pages settings.
- Confirm the page is using `https://` rather than `http://`.

### CORS error

The Flask server allows requests from:

```text
https://bostonlee05.github.io
```

Do not change the GitHub Pages repository URL without updating the
CORS origin in `src/main.py`.

### NAO cannot connect

- Confirm the NAO IP in `src/config.py`.
- Confirm the laptop and NAO are on the same network.
- Confirm NAOqi is installed for the same Python environment.
- Restart NAO and the Flask application if necessary.

## Supabase

Supabase is the database for future cloud storage. GitHub Pages and the
Cloudflare Tunnel do not migrate or replace the database automatically.

Before the database migration is complete:

- The application continues to use `src/classroom.db`.
- The public website cannot operate with Supabase until
  `src/database.py` is converted from SQLite to PostgreSQL.
