renderNav("voice.html");
document.getElementById("staticPageTitle").textContent = "Voice Recognition";
initVoiceAnimationToggle("voiceAnimationToggle");

const voiceState = {phrases: [], pendingDeleteId: null};
const $ = (id) => document.getElementById(id);

function dot(status) {
    const normalized = String(status || "");
    $("voiceStatusDot").className = "voice-dot " + (
        /error/i.test(normalized) ? "error" :
        /listen|ready|complete/i.test(normalized) ? "success" : "active"
    );
}

function renderHistory(items) {
    $("voiceHistory").innerHTML = items?.length
        ? items.map((item) => `
            <div class="voice-history-item">
                <div class="voice-history-main">
                    <span class="voice-history-command">${escapeHtml(item.command || "-")}</span>
                    <span>${escapeHtml(item.result || item.action || "")}</span>
                </div>
                <div class="voice-history-meta">
                    ${escapeHtml(item.time || item.timestamp || "")} · ${escapeHtml(item.status || "")}
                </div>
            </div>
        `).join("")
        : '<div class="voice-history-empty">No voice commands yet.</div>';
}

async function refreshVoice() {
    try {
        const [voiceResponse, robotResponse] = await Promise.all([
            apiFetch(`/api/voice/status?t=${Date.now()}`),
            apiFetch("/api/ping"),
        ]);
        const voice = voiceResponse.voice || {};
        const status = voice.status || "Ready/listening again";

        $("voiceStatusText").textContent = status;
        dot(status);
        $("latestVoiceCommand").textContent =
            voice.latest_command || "No command recognized yet.";
        $("latestVoiceResult").textContent =
            voice.latest_result || voice.latest_error || "Waiting for voice activity.";
        $("robotVoiceStatus").textContent = robotResponse.connected
            ? "NAO connected · microphone services active"
            : "NAO disconnected · voice services unavailable";
        renderHistory(voice.history || []);
    } catch (error) {
        $("voiceStatusText").textContent = "Backend unavailable";
        $("robotVoiceStatus").textContent = error.message;
        dot("Error");
    }
}

async function loadCommands() {
    try {
        const data = await apiFetch("/api/voice/commands");
        $("voiceCommands").innerHTML = data.commands?.length
            ? data.commands.map((command) => `
                <div class="voice-command-item">
                    <div>
                        <strong>${escapeHtml(command.command_key)}</strong>
                        <p>${escapeHtml(command.response || "")}</p>
                        <small>${escapeHtml((command.phrases || []).join(", "))}</small>
                    </div>
                    <button class="voice-command-delete" type="button" data-id="${command.command_id}">
                        Delete
                    </button>
                </div>
            `).join("")
            : '<div class="voice-history-empty">No predefined commands configured.</div>';
    } catch (error) {
        $("voiceCommands").textContent = error.message;
    }
}

function renderPhraseTokens() {
    $("voiceCommandPhraseTokens").innerHTML = voiceState.phrases.map((phrase, index) => `
        <button type="button" data-index="${index}" class="voice-command-token">
            ${escapeHtml(phrase)} <span aria-hidden="true">×</span>
        </button>
    `).join("");
}

function addPhrase() {
    const input = $("voiceCommandPhraseEntry");
    const value = input.value.trim().replace(/,$/, "");
    if (value && !voiceState.phrases.includes(value)) voiceState.phrases.push(value);
    input.value = "";
    renderPhraseTokens();
}

function closeModal() {
    $("voiceCommandModal").classList.add("hidden");
    $("voiceCommandForm").reset();
    voiceState.phrases = [];
    renderPhraseTokens();
}

function setVoiceDeleteModal(open) {
    $("voiceDeleteModal").classList.toggle("hidden", !open);
}

$("openVoiceCommandModal").onclick = () => $("voiceCommandModal").classList.remove("hidden");
$("closeVoiceCommandModal").onclick = closeModal;
$("cancelVoiceCommandModal").onclick = closeModal;

$("voiceCommandPhraseEntry").addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === ",") {
        event.preventDefault();
        addPhrase();
    }
});

$("voiceCommandPhraseTokens").onclick = (event) => {
    const token = event.target.closest("[data-index]");
    if (!token) return;
    voiceState.phrases.splice(Number(token.dataset.index), 1);
    renderPhraseTokens();
};

$("voiceCommandForm").onsubmit = async (event) => {
    event.preventDefault();
    addPhrase();
    try {
        await apiFetch("/api/voice/commands", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                command_key: $("voiceCommandKey").value.trim(),
                response: $("voiceCommandResponse").value.trim(),
                phrases: voiceState.phrases,
            }),
        });
        closeModal();
        await loadCommands();
    } catch (error) {
        alert(error.message);
    }
};

$("voiceCommands").onclick = (event) => {
    const button = event.target.closest("button[data-id]");
    if (!button) return;
    voiceState.pendingDeleteId = button.dataset.id;
    $("voiceDeleteName").textContent = button.closest(".voice-command-item")
        ?.querySelector("strong")?.textContent || "this command";
    setVoiceDeleteModal(true);
};

$("closeVoiceDelete").onclick = () => setVoiceDeleteModal(false);
$("cancelVoiceDelete").onclick = () => setVoiceDeleteModal(false);
$("voiceDeleteModal").onclick = (event) => {
    if (event.target.id === "voiceDeleteModal") setVoiceDeleteModal(false);
};

$("confirmVoiceDelete").onclick = async () => {
    if (!voiceState.pendingDeleteId) return;
    try {
        await apiFetch(`/api/voice/commands/${voiceState.pendingDeleteId}`, {method: "DELETE"});
        voiceState.pendingDeleteId = null;
        setVoiceDeleteModal(false);
        await loadCommands();
    } catch (error) {
        alert(error.message);
    }
};

refreshVoice();
loadCommands();
setInterval(refreshVoice, 1500);
