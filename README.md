# NAO Smart Classroom Monitoring System

## Online website

Open:

https://bostonlee05.github.io/fyp_nao/

The system has four separate parts:

| Part | Where it runs | Purpose |
|---|---|---|
| Website | GitHub Pages | User interface |
| Backend | A Windows laptop | Database, camera, AI, and robot API |
| Cloudflare Tunnel | The same Windows laptop | Gives the laptop a temporary public HTTPS address |
| Supabase | Internet | Stores database information |
| NAO robot | The same local network | Camera, speech, face registration, and voice |

The website does not contain the Supabase password or run the Python backend.

## What visitors can test

**Without a live NAO robot:**

- Subjects and student registration
- Programme management
- Subject schedules and descriptions
- Subject clash prevention
- Student edit and delete actions
- Reports and database operations
- Supabase database persistence

**With a live NAO robot:**

- Face registration
- Face recognition
- Vision monitoring
- NAO camera access
- Robot speech
- Voice recognition
- Robot connection and control

## Connecting from GitHub Pages

The computer running Flask and Cloudflare must be switched on.

1. Open https://bostonlee05.github.io/fyp_nao/.
2. Copy the active `https://...trycloudflare.com` URL from the Cloudflare terminal.
3. On the website, select **Change Backend**.
4. Paste the tunnel URL.
5. Select **Save and Connect**.
6. The site should now connect to the Flask backend.

The tunnel URL is saved in browser local storage. A quick-tunnel URL changes after
every restart, so the browser must be updated with the new URL.

---

# Laptop setup for a first-time user

Do this once on each new laptop. (Visitors do not need to install anything.)

## Step 1: Download the project

Download or clone this repository, then open it in File Explorer.

Open a terminal inside the project folder:

1. Open the project folder.
2. Hold **Shift**, right-click an empty area, and select **Open in Terminal** or **Open PowerShell window here**.

Verify that the terminal is inside the project folder by checking that it can see `requirements.txt`:

```powershell
Get-ChildItem requirements.txt
```

If PowerShell says the file is missing, use `cd` to enter the project folder first.

## Step 2: Install Python

Install Python 3.11 or the version specified in the project's virtual environment.

Check the installation:

```powershell
py --version
```

Do not continue until this prints a Python version.

## Step 3: Create a virtual environment

Run these commands from the project folder:

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt` installs the required Python libraries. It does not guarantee
that every large AI model is already downloaded.

The project may automatically download some model files on first use:

- YOLO
- InsightFace `buffalo_l`
- Faster-Whisper `base`
- Silero VAD

The first download requires internet access and may take several minutes.
Keep at least several gigabytes of free disk space available.

The exact NAOqi packages may depend on the installed Python version and the
lab environment.

## Step 4: Install Cloudflare Tunnel

Install Cloudflare Tunnel:

```powershell
winget install Cloudflare.cloudflared
```

Close and reopen PowerShell if `cloudflared` is not recognized.

If it is still not recognized, use the full executable path:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" --version
```

## Step 5: Create the `.env` file

In the project folder, create a file named `.env`.

Add:

```text
SUPABASE_DATABASE_URL=postgresql://...
GEMINI_API_KEY=...
```

Replace the examples with real values supplied by the project owner.

Do not commit or share `.env`. It contains database and AI credentials.

## Step 6: Configure the NAO IP address

Open `src/config.py` and set `ROBOT_IP` to the NAO's IP address.

The laptop and NAO must be connected to the same network.

---

# Start the project

Use two PowerShell terminals. (Can also be run on Pycharm’s built-in terminal.)

## Terminal 1: Start Flask

Open PowerShell in the project folder and run:

```powershell
.venv\Scripts\python.exe src\main.py
```

Wait until port `5000` is listening.

The server now uses the Windows WSGI server **Waitress**. You should not see
the Flask development-server warning.

Keep this terminal open.

To stop Flask, press **Ctrl+C** in this terminal.

## Terminal 2: Start Cloudflare

Open a new PowerShell window in the project folder and run:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://127.0.0.1:5000
```

Copy the generated HTTPS URL, for example:

```text
https://random-name.trycloudflare.com
```

Keep this terminal open until the demonstration ends.

To stop the tunnel, press **Ctrl+C** in this terminal.

## Terminal 3 is not normally required

Some laptops need separate terminals for Flask and Cloudflare. Do not start
either application twice unless the first copy stopped unexpectedly.

---

# Stable URL with a named tunnel

A quick tunnel creates a random URL every time it is started.

Use this option only when you need the same URL repeatedly.

## Requirements

- A Cloudflare account
- A domain owned by or assigned to the Cloudflare account
- Permission to create DNS records

## Create and configure the named tunnel

Run:

```powershell
cloudflared tunnel login
cloudflared tunnel create nao-classroom
cloudflared tunnel route dns nao-classroom nao-demo.example.com
```

Replace `nao-demo.example.com` with the approved hostname.

Start the named tunnel:

```powershell
cloudflared tunnel run --url http://127.0.0.1:5000 nao-classroom
```

Keep that terminal running during the demonstration.

To stop it, press **Ctrl+C**.

To list tunnels:

```powershell
cloudflared tunnel list
```

To delete a named tunnel:

```powershell
cloudflared tunnel delete nao-classroom
```

Delete DNS records separately in the Cloudflare dashboard if they are no longer needed.

## Quick-tunnel troubleshooting

Quick tunnels do not appear in `cloudflared tunnel list` because they are temporary.

Check for duplicate tunnel processes:

```powershell
Get-Process cloudflared -ErrorAction SilentlyContinue |
    Select-Object Id,ProcessName,Path
```

If more than one tunnel is running, stop the one you do not want.

Stop a tunnel by its process ID:

```powershell
Stop-Process -Id PROCESS_ID -Force
```

Replace `PROCESS_ID` with the actual value shown by `Get-Process`.

Quick-tunnel hostnames cannot be deleted. Closing the process expires the tunnel.
Opening a new quick tunnel creates a new hostname.

---

# Instructions for a visitor or teacher

The visitor needs:

- A web browser
- The website URL
- The currently active Cloudflare HTTPS URL

Steps:

1. Open https://bostonlee05.github.io/fyp_nao/.
2. Select **Change Backend**.
3. Paste the active Cloudflare HTTPS URL.
4. Select **Save and Connect**.
5. Use the Subjects, Students, Vision, Reports, or Voice pages.

Visitors do not need to:

- Install Python
- Install project packages
- Run Flask
- Run Cloudflare
- Open port `5000`
- View or copy `.env`
- Open Supabase

---

# Supabase setup

1. Create a Supabase project.
2. Open the Supabase SQL Editor.
3. Run the repository database migrations.
4. Confirm these tables exist:
   - `students`
   - `programmes`
   - `classes`
   - `class_enrollments`
   - `attendance_sessions`
   - `attendance`
5. Set `SUPABASE_DATABASE_URL` in the Flask laptop or backend `.env`.
6. Restart Flask after changing the database configuration.

The active database connection is PostgreSQL in `src/database.py`.
`src/classroom.db` is an archived migration source, not the active database.

---

# NAO demonstration checklist

Before the demonstration:

1. Switch on the NAO.
2. Connect the laptop and NAO to the same network.
3. Confirm the NAO IP in `src/config.py`.
4. Start Flask in Terminal 1.
5. Confirm `http://127.0.0.1:5000/api/ping` works.
6. Start Cloudflare in Terminal 2.
7. Copy the current HTTPS tunnel URL.
8. Open GitHub Pages and update **Change Backend**.
9. Confirm the header shows **Robot Connected**.

During the demonstration:

1. Register programmes and subjects.
2. Register students and assign subjects.
3. Register face data for each student.
4. Start Vision Monitoring.
5. Start an attendance session.
6. Test NAO speech and voice recognition.

---

# Troubleshooting

## The website loads but data does not

Check in this order:

1. Confirm Flask is still running.
2. Confirm Cloudflare is still running.
3. Confirm port `5000` is in use:

```powershell
Get-NetTCPConnection -State Listen |
    Where-Object LocalPort -eq 5000
```

4. Open this URL on the laptop:

```text
http://127.0.0.1:5000/api/ping
```

5. Open the website and verify that **Change Backend** contains the newest tunnel URL.

If the tunnel terminal shows `Unauthorized: Tunnel not found`, stop the old
tunnel and start a new quick tunnel.

## Two tunnels are running

List tunnel processes:

```powershell
Get-Process cloudflared -ErrorAction SilentlyContinue |
    Select-Object Id,ProcessName,Path
```

Stop duplicate processes one at a time:

```powershell
Stop-Process -Id PROCESS_ID -Force
```

Keep only one tunnel process, then copy the correct hostname from that terminal.

## Cloudflared says it cannot reach `localhost:5000`

Use IPv4 instead:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://127.0.0.1:5000
```

Also confirm Flask is running and port `5000` has a listener.

## Cloudflared is not recognized

Close and reopen PowerShell after installation, or run:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://127.0.0.1:5000
```

## CORS error

Flask allows:

```text
https://bostonlee05.github.io
```

If the GitHub Pages domain changes, update `CORS(app, ...)` in `src/main.py`.

## Supabase connection fails

- Confirm `.env` contains `SUPABASE_DATABASE_URL`.
- Use the Supabase Session pooler URI if direct IPv6 DNS is unavailable.
- URL-encode special characters in the database password.
- Confirm required tables and foreign keys exist.
- Restart Flask after changing `.env`.
- Rotate a database password if it was shared publicly.

## NAO cannot connect

- Confirm the NAO IP in `src/config.py`.
- Confirm the laptop and NAO are on the same network.
- Confirm the NAO is switched on.
- Confirm the required NAOqi packages match the Python environment.
- Restart Flask after changing the robot IP.
- Check whether the header displays **Robot Connected**.

## Camera preview is slow or missing

- Confirm NAO and laptop are on the same network.
- Select **Start Vision** and wait for the camera status to change.
- Confirm no other process is subscribed to the camera.
- Restart Flask if the NAO camera subscription is stuck.
- Reopen the GitHub Pages vision page and press **Start Vision** again.

## The laptop or tunnel is switched off

GitHub Pages and Supabase remain available, but the Flask backend is not.

To make the project usable without the lab laptop:

1. Deploy Flask/Waitress to a permanent server or cloud host.
2. Configure Supabase and `.env` on that server.
3. Install and configure the robot packages only if the robot stays on that server network.
4. Enter the server HTTPS URL in **Change Backend**.

Until a permanent backend is deployed, someone must run Flask and Cloudflare
on the laptop for the GitHub Pages frontend to access the application.
