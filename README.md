# NAO Smart Classroom Monitoring System

## Online website

The public frontend is hosted on GitHub Pages:

https://bostonlee05.github.io/fyp_nao/

The frontend, backend, database, and robot are separate parts:

| Component | Location | Purpose |
|---|---|---|
| GitHub Pages | GitHub | Browser interface |
| Flask | Laptop or backend host | API and server-side application |
| Cloudflare Tunnel | Laptop or backend host | Gives Flask a public HTTPS URL |
| Supabase PostgreSQL | Supabase cloud | Persistent database |
| NAO robot | Lab network | Camera, voice, speech, and robot features |

Supabase is used instead of `src/classroom.db` or `classroom.db`.
Visitors do not need to install Python or Cloudflare.

## What visitors can test

Without the NAO:

- Subjects and student registration
- Programme management
- Subject descriptions and schedules
- Subject clash prevention
- Student edit and delete actions
- Reports and database operations
- Supabase data persistence

The NAO is required for:

- Face registration
- Face recognition
- Vision monitoring
- NAO camera access
- Robot speech
- Voice recognition
- Robot control

## Connecting from GitHub Pages

1. Open https://bostonlee05.github.io/fyp_nao/.
2. Enter the currently active Cloudflare HTTPS URL.
3. Select **Save and Connect**.
4. Use the website normally.

The tunnel URL is stored in that browser's local storage. It must be
entered again if the browser data is cleared or the tunnel URL changes.

## Laptop host setup

Use this procedure when the lab laptop is the backend host.

### 1. Install requirements

```powershell
cd C:\Users\Boston\PycharmProjects\fyp_nao
py -m venv .venv
.\.venv\Scripts\Activate.ps1

py -m pip install flask flask-cors psycopg2-binary python-dotenv
py -m pip install ultralytics insightface deep-sort-realtime
py -m pip install numpy opencv-python pyttsx3 requests google-genai
py -m pip install faster-whisper torch
```

The exact NAOqi and AI packages required for full robot operation depend
on the installed Python version and the lab environment.

Install Cloudflare Tunnel:

```powershell
winget install Cloudflare.cloudflared
```

The executable may be installed under:

```text
C:\Program Files (x86)\cloudflared\cloudflared.exe
```

### 2. Configure environment variables

Create or update `.env` in the repository root:

```text
SUPABASE_DATABASE_URL=postgresql://...
GEMINI_API_KEY=...
```

Do not commit `.env`. It is excluded by `.gitignore`.
Never put a database password or API key in GitHub Pages JavaScript.

### 3. Start Flask

Open the first terminal:

```powershell
cd C:\Users\Boston\PycharmProjects\fyp_nao
.\.venv\Scripts\Activate.ps1
py src\main.py
```

Flask should listen on port `5000`.

The application automatically switches to Web-Only Mode if the NAO cannot
be reached. Students, subjects, programmes, reports, and Supabase features
remain available.

### 4. Start the public tunnel

Open a second terminal:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:5000
```

Copy the HTTPS URL printed by Cloudflare. It normally looks like:

```text
https://random-name.trycloudflare.com
```

Keep both Flask and Cloudflare running until the demonstration ends.

If `cloudflared` is not recognized, use the executable path above or
restart PowerShell after adding the Cloudflare installation directory to
the user `PATH`.

## Stable URL with a named tunnel

A quick tunnel creates a random URL. It may change whenever Cloudflare or
the laptop restarts.

For a stable hostname, use a Cloudflare account and a domain:

```powershell
cloudflared tunnel login
cloudflared tunnel create nao-classroom
cloudflared tunnel route dns nao-classroom nao-demo.example.com
cloudflared tunnel run --url http://localhost:5000 nao-classroom
```

Replace `nao-demo.example.com` with the approved domain.
Keep the named-tunnel command running during demonstrations.

## Instructions for another student or teacher

The visitor needs only an internet browser and the current tunnel URL.

1. Open https://bostonlee05.github.io/fyp_nao/.
2. Enter the tunnel URL shared by the backend host.
3. Select **Save and Connect**.
4. Open **Subjects & Students**, **Attendance**, or **Reports**.

The visitor must not:

- Run Flask
- Install Python packages
- Open port `5000`
- Install Cloudflare
- Copy or view the Supabase password
- Open Supabase

If the laptop or tunnel stops, the website will remain visible but API
requests will stop working.

## When the laptop is switched off

GitHub Pages and Supabase continue to be available, but the Flask backend
is not.

To make the website usable without the lab laptop:

1. Deploy Flask to a permanent server or cloud host.
2. Configure Supabase and `.env` on that server.
3. Install robot packages only if the robot remains connected.
4. Set the server's HTTPS URL as the frontend API base URL.

Until that deployment exists, a computer must run Flask and Cloudflare
tunnel for the frontend to process application data.

## Supabase setup

1. Create a Supabase project.
2. Run the table migrations in **SQL Editor**.
3. Keep these tables:
   - `students`
   - `programmes`
   - `classes`
   - `class_enrollments`
   - `attendance_sessions`
   - `attendance`
4. Set `SUPABASE_DATABASE_URL` in the Flask laptop or backend `.env`.
5. Restart Flask after changing the database configuration.

The active database connection is PostgreSQL in `src/database.py`.
`src/classroom.db` is an archived migration source and is not the active
database.

## NAO demonstration checklist

1. Switch on the NAO.
2. Connect the laptop and NAO to the same network.
3. Configure the NAO IP in `src/config.py`.
4. Start Flask.
5. Start Cloudflare.
6. Open the GitHub Pages website.
7. Enter the current tunnel URL.
8. Register students and subjects.
9. Register face data.
10. Start vision and attendance.
11. Test NAO speech and voice recognition.

## Troubleshooting

### The frontend loads but data does not

- Confirm Flask is running.
- Confirm Cloudflare is running.
- Confirm the browser is using the newest tunnel URL.
- Test `http://localhost:5000/api/status` on the laptop.

### CORS error

Flask allows:

```text
https://bostonlee05.github.io
```

Update `CORS(app, ...)` in `src/main.py` if the GitHub Pages domain changes.

### Cloudflared is not recognized

Use the absolute executable path:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:5000
```

### Supabase connection fails

- Confirm `.env` contains `SUPABASE_DATABASE_URL`.
- Use the Supabase Session pooler URI when direct IPv6 DNS is unavailable.
- URL-encode special characters in the database password.
- Confirm the tables and foreign keys exist.
- Rotate any database password previously shared publicly.

### NAO cannot connect

- Confirm the NAO IP in `src/config.py`.
- Confirm the laptop and NAO are on the same network.
- Confirm the required NAOqi packages match the Python environment.
- Restart Flask after changing the robot configuration.
