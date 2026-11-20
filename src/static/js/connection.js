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

const voiceStatusText = document.getElementById("voiceStatusText");
const voiceStatusDot = document.getElementById("voiceStatusDot");
const latestVoiceCommand = document.getElementById("latestVoiceCommand");
const latestVoiceResult = document.getElementById("latestVoiceResult");
const voiceHistory = document.getElementById("voiceHistory");
const voiceCommands = document.getElementById("voiceCommands");
const voiceCommandModal = document.getElementById("voiceCommandModal");
const voiceDeleteModal = document.getElementById("voiceDeleteModal");
const openVoiceCommandModal = document.getElementById("openVoiceCommandModal");
const closeVoiceCommandModal = document.getElementById("closeVoiceCommandModal");
const cancelVoiceCommandModal = document.getElementById("cancelVoiceCommandModal");
const voiceCommandForm = document.getElementById("voiceCommandForm");
const voiceCommandKey = document.getElementById("voiceCommandKey");
const voiceCommandResponse = document.getElementById("voiceCommandResponse");
const voiceCommandPhraseTokens = document.getElementById("voiceCommandPhraseTokens");
const voiceCommandPhraseEntry = document.getElementById("voiceCommandPhraseEntry");
let voiceCommandPhrases = [];
let pendingVoiceDeleteId = null;
const searchRecommendationToast = document.getElementById("searchRecommendationToast");
const searchRecommendationList = document.getElementById("searchRecommendationList");
const searchToastClose = document.getElementById("searchToastClose");
const robotDisconnectPopup = document.getElementById("robotDisconnectPopup");
const robotDisconnectClose = document.getElementById("robotDisconnectClose");

let lastRecommendationToken = 0;
let voiceStatusRequestInFlight = false;
let manualRobotDisconnectRequested = false;
let lastRobotConnectedState =
    Boolean(window.ROBOT_STATUS && window.ROBOT_STATUS.connected);


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

function showRobotDisconnectedPopup(reason = "") {
    if (!robotDisconnectPopup) return;

    const message = document.getElementById("robotDisconnectMessage");
    if (message) {
        message.textContent = reason
            ? `The NAO robot connection was lost: ${reason}`
            : "The NAO robot connection was lost. Reconnect it before continuing.";
    }

    robotDisconnectPopup.classList.remove("hidden");
}

if (robotDisconnectClose && robotDisconnectPopup) {
    robotDisconnectClose.addEventListener("click", () => {
        robotDisconnectPopup.classList.add("hidden");
    });
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
    manualRobotDisconnectRequested = true;

    try {

        const response = await fetch("/api/disconnect", {

            method: "POST"

        });

        const result = await response.json();

        if (result.success) {

            setDisconnectedUI("Disconnected");

            addLog("Robot disconnected.");

            updateDashboard(result.status);
            manualRobotDisconnectRequested = false;

        }

        else {

            addLog(result.message);
            manualRobotDisconnectRequested = false;

        }

    }

    catch (err) {

        console.error(err);
        manualRobotDisconnectRequested = false;

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

    const connected = Boolean(data.connected);
    if (
        lastRobotConnectedState &&
        !connected &&
        !manualRobotDisconnectRequested
    ) {
        showRobotDisconnectedPopup(data.last_disconnect_reason || "");
    }
    if (connected && robotDisconnectPopup) {
        robotDisconnectPopup.classList.add("hidden");
    }
    lastRobotConnectedState = connected;

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
// Voice Recognition UI
// ======================================================

function escapeHtml(value) {

    return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");

}

function setVoiceDot(status) {

    if (!voiceStatusDot) return;

    voiceStatusDot.className = "voice-dot";

    const normalized = String(status || "").toLowerCase();

    if (normalized.includes("error")) {
        voiceStatusDot.classList.add("error");
        return;
    }

    if (
        normalized.includes("completed")
        || normalized.includes("ready")
        || normalized.includes("waiting")
    ) {
        voiceStatusDot.classList.add("success");
        return;
    }

    voiceStatusDot.classList.add("active");

}

function renderVoiceHistory(history) {

    if (!voiceHistory) return;

    if (!history || history.length === 0) {
        voiceHistory.innerHTML =
            '<div class="voice-history-empty">No voice commands yet.</div>';
        return;
    }

    voiceHistory.innerHTML = history.map((item) => {
        const command = escapeHtml(item.command || "No command");
        const action = escapeHtml(item.action || "Unknown");
        const status = escapeHtml(item.status || "Completed");
        const time = escapeHtml(item.time || "--:--");

        return `
            <div class="voice-history-item">
                <div class="voice-history-main">
                    <span>${time}</span>
                    <span class="voice-history-command">"${command}"</span>
                </div>
                <div class="voice-history-meta">
                    ${action} - ${status}
                </div>
            </div>
        `;
    }).join("");

}

function renderVoiceCommands(commands) {

    if (!voiceCommands) return;

    if (!commands || commands.length === 0) {
        voiceCommands.innerHTML =
            '<div class="voice-history-empty">No predefined commands configured.</div>';
        return;
    }

    voiceCommands.innerHTML = commands.map((command) => {
        const key = escapeHtml(command.command_key || "Unnamed command");
        const response = escapeHtml(command.response || "");
        const triggers = (command.triggers || []) /*
            .map((trigger) => `“${escapeHtml(trigger)}”`)
            .join(", ");

        */
        const triggerText = triggers
            .map((trigger) => '"' + escapeHtml(trigger) + '"')
            .join(", ");
        return `
            <div class="voice-command-item">
                <div>
                    <strong>${key}</strong>
                    <p>${response}</p>
                    <small>Trigger phrases: ${triggerText || "None"}</small>
                </div>
                <button class="voice-command-delete" type="button"
                        data-command-id="${escapeHtml(command.command_id)}">
                    Delete
                </button>
            </div>
        `;
    }).join("");

}

function setVoiceCommandModalOpen(isOpen) {
    if (!voiceCommandModal) return;

    voiceCommandModal.classList.toggle("hidden", !isOpen);
    document.body.classList.toggle("voice-command-modal-open", isOpen);

    if (isOpen && voiceCommandKey) {
        voiceCommandKey.focus();
    }
}

function setVoiceDeleteModalOpen(isOpen) {
    if (!voiceDeleteModal) return;
    voiceDeleteModal.classList.toggle("hidden", !isOpen);
    document.body.classList.toggle("voice-command-modal-open", isOpen);
}

function renderVoiceCommandPhraseTokens() {
    if (!voiceCommandPhraseTokens) return;

    voiceCommandPhraseTokens.innerHTML = voiceCommandPhrases.map((phrase, index) => `
        <button class="voice-command-token" type="button" data-token-index="${index}"
                title="Remove ${escapeHtml(phrase)}">
            <span>${escapeHtml(phrase)}</span>
            <span aria-hidden="true">&times;</span>
        </button>
    `).join("");
}

function addVoiceCommandPhrase(value) {
    const phrase = value.trim();
    if (!phrase) return;

    const normalized = phrase.toLowerCase().replace(/\s+/g, " ");
    if (!voiceCommandPhrases.some((item) => item.toLowerCase() === normalized)) {
        voiceCommandPhrases.push(phrase);
        renderVoiceCommandPhraseTokens();
    }
}

function commitVoiceCommandPhraseInput() {
    if (!voiceCommandPhraseEntry) return;

    voiceCommandPhraseEntry.value
        .split(",")
        .forEach(addVoiceCommandPhrase);
    voiceCommandPhraseEntry.value = "";
}

function resetVoiceCommandPhraseInput() {
    voiceCommandPhrases = [];
    if (voiceCommandPhraseEntry) voiceCommandPhraseEntry.value = "";
    renderVoiceCommandPhraseTokens();
}

async function saveVoiceCommand(event) {
    event.preventDefault();

    commitVoiceCommandPhraseInput();
    if (voiceCommandPhrases.length === 0) {
        alert("Add at least one trigger phrase.");
        voiceCommandPhraseEntry.focus();
        return;
    }

    try {
        const response = await fetch("/api/voice/commands", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                command_key: voiceCommandKey.value.trim(),
                response: voiceCommandResponse.value.trim(),
                phrases: voiceCommandPhrases,
            }),
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.message || "Could not save voice command");
        }

        renderVoiceCommands(result.commands);
        voiceCommandForm.reset();
        resetVoiceCommandPhraseInput();
        setVoiceCommandModalOpen(false);
    } catch (error) {
        alert(error.message);
    }
}

async function deleteVoiceCommand(commandId) {
    pendingVoiceDeleteId = commandId;
    setVoiceDeleteModalOpen(true);
}

async function confirmVoiceCommandDelete() {
    const commandId = pendingVoiceDeleteId;
    if (!commandId) return;
    pendingVoiceDeleteId = null;
    setVoiceDeleteModalOpen(false);

    try {
        const response = await fetch(
            `/api/voice/commands/${encodeURIComponent(commandId)}`,
            { method: "DELETE" }
        );
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.message || "Could not delete voice command");
        }

        renderVoiceCommands(result.commands);
    } catch (error) {
        alert(error.message);
    }
}

if (voiceCommandForm) {
    voiceCommandForm.addEventListener("submit", saveVoiceCommand);
}

if (voiceCommandPhraseEntry) {
    voiceCommandPhraseEntry.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === ",") {
            event.preventDefault();
            commitVoiceCommandPhraseInput();
        }
    });
    voiceCommandPhraseEntry.addEventListener("blur", commitVoiceCommandPhraseInput);
}

if (voiceCommandPhraseTokens) {
    voiceCommandPhraseTokens.addEventListener("click", (event) => {
        const token = event.target.closest("[data-token-index]");
        if (!token) return;

        voiceCommandPhrases.splice(Number(token.dataset.tokenIndex), 1);
        renderVoiceCommandPhraseTokens();
    });
}

if (openVoiceCommandModal) {
    openVoiceCommandModal.addEventListener("click", () => {
        resetVoiceCommandPhraseInput();
        setVoiceCommandModalOpen(true);
    });
}

if (closeVoiceCommandModal) {
    closeVoiceCommandModal.addEventListener("click", () => {
        setVoiceCommandModalOpen(false);
    });
}

if (cancelVoiceCommandModal) {
    cancelVoiceCommandModal.addEventListener("click", () => {
        voiceCommandForm.reset();
        resetVoiceCommandPhraseInput();
        setVoiceCommandModalOpen(false);
    });
}

if (voiceCommandModal) {
    voiceCommandModal.addEventListener("click", (event) => {
        if (event.target === voiceCommandModal) {
            setVoiceCommandModalOpen(false);
        }
    });
}

if (voiceDeleteModal) {
    voiceDeleteModal.addEventListener("click", (event) => {
        if (event.target === voiceDeleteModal) {
            pendingVoiceDeleteId = null;
            setVoiceDeleteModalOpen(false);
        }
    });
}

document.getElementById("closeVoiceDeleteModal")?.addEventListener("click", () => {
    pendingVoiceDeleteId = null;
    setVoiceDeleteModalOpen(false);
});

document.getElementById("cancelVoiceDelete")?.addEventListener("click", () => {
    pendingVoiceDeleteId = null;
    setVoiceDeleteModalOpen(false);
});

document.getElementById("confirmVoiceDelete")?.addEventListener("click", confirmVoiceCommandDelete);

document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && voiceCommandModal &&
        !voiceCommandModal.classList.contains("hidden")) {
        setVoiceCommandModalOpen(false);
    }
    if (event.key === "Escape" && voiceDeleteModal &&
        !voiceDeleteModal.classList.contains("hidden")) {
        pendingVoiceDeleteId = null;
        setVoiceDeleteModalOpen(false);
    }
});

if (voiceCommands) {
    voiceCommands.addEventListener("click", (event) => {
        const button = event.target.closest("[data-command-id]");
        if (button) deleteVoiceCommand(button.dataset.commandId);
    });
}

async function fetchVoiceCommands() {

    if (!voiceCommands) return;

    try {
        const response = await fetch(`/api/voice/commands?t=${Date.now()}`, {
            cache: "no-store",
        });
        const result = await response.json();

        if (!response.ok || !result.success)
            throw new Error(result.message || "Voice commands unavailable");

        renderVoiceCommands(result.commands);
    } catch (error) {
        voiceCommands.innerHTML =
            `<div class="voice-history-empty">${escapeHtml(error.message)}</div>`;
    }

}

function renderSearchRecommendations(recommendations) {

    if (!searchRecommendationToast || !searchRecommendationList) return;

    if (!recommendations || recommendations.length === 0) {
        searchRecommendationList.innerHTML =
            '<div class="search-toast-empty">No search results found.</div>';
        searchRecommendationToast.classList.remove("hidden");
        return;
    }

    searchRecommendationList.innerHTML = recommendations.map((item) => {
        const title = escapeHtml(item.title || "Untitled result");
        const url = escapeHtml(item.url || "#");
        const thumbnail = escapeHtml(item.thumbnail || "");

        return `
            <a class="search-toast-item" href="${url}" target="_blank" rel="noopener noreferrer">
                <img class="search-toast-thumbnail" src="${thumbnail}" alt="" loading="lazy" onerror="this.classList.add('thumbnail-failed')">
                <span class="search-toast-copy">
                    <span class="search-toast-title">${title}</span>
                    <span class="search-toast-url">${url}</span>
                </span>
            </a>
        `;
    }).join("");

    searchRecommendationToast.classList.remove("hidden");

}

function updateVoiceDashboard(voice) {

    if (!voice) return;

    if (voiceStatusText)
        voiceStatusText.textContent = voice.status || "Ready/listening again";

    setVoiceDot(voice.status);

    if (latestVoiceCommand)
        latestVoiceCommand.textContent =
            voice.latest_command || "No command recognized yet.";

    if (latestVoiceResult)
        latestVoiceResult.textContent =
            voice.latest_result || voice.latest_error || "Waiting for voice activity.";

    renderVoiceHistory(voice.history);

    if (
        voice.recommendation_token
        && voice.recommendation_token !== lastRecommendationToken
    ) {
        lastRecommendationToken = voice.recommendation_token;
        renderSearchRecommendations(voice.recommendations || []);
    }

}

async function fetchVoiceStatus() {

    if (voiceStatusRequestInFlight) return;
    voiceStatusRequestInFlight = true;

    try {

        const response = await fetch(`/api/voice/status?t=${Date.now()}`, {
            cache: "no-store",
        });

        if (!response.ok)
            throw new Error("Voice status API unavailable");

        const result = await response.json();

        if (result.success)
            updateVoiceDashboard(result.voice);

    }

    catch (err) {

        console.error(err);

        if (voiceStatusText)
            voiceStatusText.textContent = "Error";

        setVoiceDot("Error");

    } finally {
        voiceStatusRequestInFlight = false;
    }

}

if (searchToastClose) {

    searchToastClose.addEventListener("click", () => {

        searchRecommendationToast.classList.add("hidden");

    });

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

// Voice status
setInterval(fetchVoiceStatus, 750);



// ======================================================
// Initial Load
// ======================================================

document.addEventListener("DOMContentLoaded", () => {

    fetchStatus();

    refreshSession();

    fetchVoiceStatus();
    fetchVoiceCommands();

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

        fetchVoiceStatus();

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

    fetchVoiceStatus();

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
