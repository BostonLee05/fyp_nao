// ======================================================
// connection.js
// NAO Smart Classroom Dashboard
// Version 4
// ======================================================


// ======================================================
// Cached HTML Elements
// ======================================================

const sidebar = document.getElementById("sidebar");
const toggleBtn = document.getElementById("toggleBtn");

const connectBtn = document.getElementById("connectBtn");
const disconnectBtn = document.getElementById("disconnectBtn");

const robotIPInput = document.getElementById("robot_ip");
const sessionDuration = document.getElementById("sessionDuration");

const statusBox = document.getElementById("status");

const robotCard = document.getElementById("robotCard");
const cameraCard = document.getElementById("cameraCard");
const attendanceCard = document.getElementById("attendanceCard");
const studentCard = document.getElementById("studentCard");

const sessionStatus = document.getElementById("sessionStatus");
const robotIP = document.getElementById("robotIP");
const sessionID = document.getElementById("sessionID");
const remainingTime = document.getElementById("remainingTime");
const disconnectReason = document.getElementById("disconnectReason");

const robotStatusText = document.getElementById("robotStatusText");
const robotStatusPill = document.getElementById("robotStatusPill");

const logBox = document.getElementById("log");

const clock = document.getElementById("clock");


// ======================================================
// Sidebar
// ======================================================

if (toggleBtn) {

    if (localStorage.getItem("sidebarCollapsed") === "true") {

        sidebar.classList.add("collapsed");

    }

    toggleBtn.onclick = () => {

        sidebar.classList.toggle("collapsed");

        localStorage.setItem(
            "sidebarCollapsed",
            sidebar.classList.contains("collapsed")
        );

    };

}


// ======================================================
// Clock
// ======================================================

function updateClock() {

    if (!clock) return;

    const now = new Date();

    clock.textContent = now.toLocaleTimeString();

}

updateClock();

setInterval(updateClock, 1000);


// ======================================================
// Activity Log
// ======================================================

function addLog(message) {

    if (!logBox) return;

    const div = document.createElement("div");

    const now = new Date().toLocaleTimeString();

    div.innerHTML = `[${now}] ${message}`;

    logBox.prepend(div);

}


// ======================================================
// Helpers
// ======================================================

function setConnectedUI() {

    if (robotCard)
        robotCard.textContent = "Connected";

    if (robotStatusText)
        robotStatusText.textContent = "Robot Connected";

    if (robotStatusPill) {

        robotStatusPill.classList.remove("disconnected");
        robotStatusPill.classList.add("connected");

    }

    if (statusBox) {

        statusBox.className = "status connected";
        statusBox.innerHTML = "🟢 Connected";

    }

}

function setDisconnectedUI(reason = "Offline") {

    if (robotCard)
        robotCard.textContent = "Offline";

    if (robotStatusText)
        robotStatusText.textContent = "Robot Offline";

    if (robotStatusPill) {

        robotStatusPill.classList.remove("connected");
        robotStatusPill.classList.add("disconnected");

    }

    if (statusBox) {

        statusBox.className = "status disconnected";
        statusBox.innerHTML = "🔴 " + reason;

    }

}

// ======================================================
// Connect Robot
// ======================================================

async function connectRobot() {

    if (!robotIPInput) return;

    const ip = robotIPInput.value.trim();

    if (ip === "") {

        setDisconnectedUI("Please enter Robot IP.");

        addLog("Connection failed (No IP entered).");

        return;

    }

    const durationValue = sessionDuration
        ? sessionDuration.value
        : "";

    let duration = null;

    if (durationValue !== "") {

        duration = parseInt(durationValue);

    }

    connectBtn.disabled = true;

    connectBtn.innerHTML = "Connecting...";

    try {

        const response = await fetch("/api/connect", {

            method: "POST",

            headers: {

                "Content-Type": "application/json"

            },

            body: JSON.stringify({

                ip: ip,

                duration: duration

            })

        });

        const result = await response.json();

        if (result.success) {

            setConnectedUI();

            addLog("Robot connected.");

            updateDashboard(result.status);

        }

        else {

            setDisconnectedUI(result.message);

            addLog(result.message);

        }

    }

    catch (err) {

        console.error(err);

        setDisconnectedUI("Server Error");

        addLog("Unable to connect to server.");

    }

    connectBtn.disabled = false;

    connectBtn.innerHTML = "Connect Robot";

}



// ======================================================
// Disconnect Robot
// ======================================================

async function disconnectRobot() {

    disconnectBtn.disabled = true;

    disconnectBtn.innerHTML = "Disconnecting...";

    try {

        const response = await fetch("/api/disconnect", {

            method: "POST"

        });

        const result = await response.json();

        if (result.success) {

            setDisconnectedUI("Disconnected");

            addLog("Robot disconnected.");

            updateDashboard(result.status);

        }

        else {

            addLog(result.message);

        }

    }

    catch (err) {

        console.error(err);

        addLog("Unable to disconnect robot.");

    }

    disconnectBtn.disabled = false;

    disconnectBtn.innerHTML = "Disconnect Robot";

}



// ======================================================
// Button Events
// ======================================================

if (connectBtn) {

    connectBtn.addEventListener(

        "click",

        connectRobot

    );

}

if (disconnectBtn) {

    disconnectBtn.addEventListener(

        "click",

        disconnectRobot

    );

}



// ======================================================
// Press ENTER to connect
// ======================================================

if (robotIPInput) {

    robotIPInput.addEventListener(

        "keypress",

        function(e){

            if(e.key==="Enter"){

                connectRobot();

            }

        }

    );

}

// ======================================================
// Dashboard Update
// ======================================================

function updateDashboard(data) {

    if (!data) return;

    // -------------------------------
    // Robot Status
    // -------------------------------

    if (sessionStatus)
        sessionStatus.textContent = data.connected
            ? "Connected"
            : "Disconnected";

    if (robotIP)
        robotIP.textContent = data.robot_ip || "-";

    if (sessionID)
        sessionID.textContent = data.session_id || "-";

    if (remainingTime)
        remainingTime.textContent = data.remaining || "Expired";

    if (disconnectReason)
        disconnectReason.textContent =
            data.last_disconnect_reason || "-";

    // -------------------------------
    // Button States
    // -------------------------------

    if (connectBtn)
        connectBtn.disabled = data.connected;

    if (disconnectBtn)
        disconnectBtn.disabled = !data.connected;

    // -------------------------------
    // Robot Status Card
    // -------------------------------

    if (data.connected)
        setConnectedUI();
    else
        setDisconnectedUI("Offline");

}



// ======================================================
// Poll Backend Status
// ======================================================

async function fetchStatus() {

    try {

        const response = await fetch("/api/status");

        if (!response.ok)
            throw new Error("Status API unavailable");

        const result = await response.json();

        if (result.success) {

            updateDashboard(result.status);

        }

    }

    catch (err) {

        console.error(err);

        setDisconnectedUI("Server Offline");

    }

}



// ======================================================
// Session Countdown Refresh
// ======================================================

async function refreshSession() {

    try {

        const response = await fetch("/api/session");

        if (!response.ok)
            return;

        const result = await response.json();

        if (!result.success)
            return;

        const session = result.session;

        if (remainingTime) {

            remainingTime.textContent =
                session.remaining || "Expired";

        }

    }

    catch (err) {

        console.error(err);

    }

}



// ======================================================
// Ping Robot
// ======================================================

async function pingRobot() {

    try {

        const response = await fetch("/api/ping");

        if (!response.ok)
            return;

        const result = await response.json();

        if (!result.success)
            return;

        // Future:
        // heartbeat, latency,
        // battery, camera FPS, etc.

    }

    catch (err) {

        console.error(err);

    }

}



// ======================================================
// Automatic Polling
// ======================================================

// Robot status
setInterval(fetchStatus, 2000);

// Session countdown
setInterval(refreshSession, 1000);

// Robot heartbeat
setInterval(pingRobot, 5000);



// ======================================================
// Initial Load
// ======================================================

document.addEventListener("DOMContentLoaded", () => {

    fetchStatus();

    refreshSession();

    addLog("Dashboard initialized.");

});

// ======================================================
// Network Status
// ======================================================

window.addEventListener("offline", () => {

    setDisconnectedUI("No Internet");

    addLog("Internet connection lost.");

});

window.addEventListener("online", () => {

    addLog("Internet connection restored.");

    fetchStatus();

});



// ======================================================
// Page Visibility
// ======================================================

document.addEventListener("visibilitychange", () => {

    if (document.hidden) {

        addLog("Dashboard hidden.");

    } else {

        addLog("Dashboard active.");

        fetchStatus();

        refreshSession();

    }

});



// ======================================================
// Utility Functions
// ======================================================

function formatTime(seconds) {

    if (seconds === null || seconds === undefined)
        return "--";

    seconds = Number(seconds);

    if (isNaN(seconds))
        return "--";

    if (seconds < 0)
        seconds = 0;

    const hrs = Math.floor(seconds / 3600);

    const mins = Math.floor((seconds % 3600) / 60);

    const secs = Math.floor(seconds % 60);

    if (hrs > 0) {

        return `${hrs}h ${mins}m ${secs}s`;

    }

    if (mins > 0) {

        return `${mins}m ${secs}s`;

    }

    return `${secs}s`;

}



// ======================================================
// Future Module Hooks
// ======================================================

// Live Camera
function refreshCamera() {

    // Future implementation

}

// Attendance
function refreshAttendance() {

    // Future implementation

}

// Behaviour Detection
function refreshBehaviour() {

    // Future implementation

}


// Reports
function refreshReports() {

    // Future implementation

}



// Robot Control
function refreshRobotControl() {

    // Future implementation

}



// ======================================================
// Safe Dashboard Refresh
// ======================================================

function refreshEverything() {

    fetchStatus();

    refreshSession();

    refreshCamera();

    refreshAttendance();

    refreshBehaviour();

    refreshReports();

    refreshRobotControl();

}



// ======================================================
// Auto Refresh Every Minute
// ======================================================

setInterval(() => {

    refreshEverything();

}, 60000);



// ======================================================
// Welcome Log
// ======================================================

addLog("NAO Smart Classroom Dashboard Ready.");



// ======================================================
// Debug (Remove in Production)
// ======================================================

window.dashboard = {

    connectRobot,

    disconnectRobot,

    fetchStatus,

    refreshEverything

};

console.log("connection.js loaded successfully.");