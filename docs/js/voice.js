renderNav("voice.html");
document.getElementById("staticPageTitle").textContent = "Voice Recognition";
initVoiceAnimationToggle("voiceAnimationToggle");

const voiceState = {
    phrases: [],
    pendingDeleteId: null,
    editingCommandId: null,
    lastRecommendationToken: 0,
};
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

function renderSearchRecommendations(recommendations) {
    const toast = $("searchRecommendationToast");
    const list = $("searchRecommendationList");
    if (!toast || !list) return;

    if (!recommendations?.length) {
        list.innerHTML = '<div class="search-toast-empty">No search results found.</div>';
        toast.classList.remove("hidden");
        return;
    }

    list.innerHTML = recommendations.map((item) => {
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

    toast.classList.remove("hidden");
}

async function refreshVoice() {
    try {
        const voiceResponse = await apiFetch(`/api/voice/status?t=${Date.now()}`);
        const voice = voiceResponse.voice || {};
        const status = voice.status || "Ready/listening again";

        $("voiceStatusText").textContent = status;
        dot(status);
        $("latestVoiceCommand").textContent =
            voice.latest_command || "No command recognized yet.";
        $("latestVoiceResult").textContent =
            voice.latest_result || voice.latest_error || "Waiting for voice activity.";
        renderHistory(voice.history || []);
        if (
            voice.recommendation_token
            && voice.recommendation_token !== voiceState.lastRecommendationToken
        ) {
            voiceState.lastRecommendationToken = voice.recommendation_token;
            renderSearchRecommendations(voice.recommendations || []);
        }
    } catch (error) {
        $("voiceStatusText").textContent = "Backend unavailable";
        const robotVoiceStatus = $("robotVoiceStatus");
        if (robotVoiceStatus) robotVoiceStatus.textContent = error.message;
        dot("Error");
        return;
    }

    // A robot-status failure should not hide a valid voice backend response.
    try {
        const robotResponse = await apiFetch(`/api/ping?t=${Date.now()}`);
        const robotVoiceStatus = $("robotVoiceStatus");
        if (robotVoiceStatus) robotVoiceStatus.textContent = robotResponse.connected
            ? "NAO connected · microphone services active"
            : "NAO disconnected · voice services unavailable";
    } catch (error) {
        const robotVoiceStatus = $("robotVoiceStatus");
        if (robotVoiceStatus) robotVoiceStatus.textContent = "Robot status unavailable";
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
                        <small>${escapeHtml((command.triggers || command.phrases || []).join(", "))}</small>
                    </div>
                    <div class="action-buttons voice-command-actions">
                        <button class="action-btn edit-btn" type="button" data-action="edit" data-id="${command.command_id}">Edit</button>
                        <button class="action-btn delete-btn" type="button" data-action="delete" data-id="${command.command_id}">Delete</button>
                    </div>
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
    voiceState.editingCommandId = null;
    $("voiceCommandModalTitle").textContent = "Add Predefined Command";
    $("saveVoiceCommandButton").textContent = "Save Command";
    renderPhraseTokens();
}

function openAddModal() {
    closeModal();
    $("voiceCommandModal").classList.remove("hidden");
    $("voiceCommandKey").focus();
}

function openEditModal(command) {
    voiceState.editingCommandId = command.command_id;
    voiceState.phrases = [...(command.triggers || command.phrases || [])];
    $("voiceCommandKey").value = command.command_key || "";
    $("voiceCommandResponse").value = command.response || "";
    $("voiceCommandModalTitle").textContent = "Edit Predefined Command";
    $("saveVoiceCommandButton").textContent = "Update Command";
    renderPhraseTokens();
    $("voiceCommandModal").classList.remove("hidden");
    $("voiceCommandKey").focus();
}

function setVoiceDeleteModal(open) {
    $("voiceDeleteModal").classList.toggle("hidden", !open);
}

$("openVoiceCommandModal").onclick = openAddModal;
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
        const commandId = voiceState.editingCommandId;
        await apiFetch(commandId ? `/api/voice/commands/${commandId}` : "/api/voice/commands", {
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
    const command = button.closest(".voice-command-item");
    if (button.dataset.action === "edit") {
        openEditModal({
            command_id: button.dataset.id,
            command_key: command?.querySelector("strong")?.textContent || "",
            response: command?.querySelector("p")?.textContent || "",
            triggers: (command?.querySelector("small")?.textContent || "").split(", ").filter(Boolean),
        });
        return;
    }
    voiceState.pendingDeleteId = button.dataset.id;
    $("voiceDeleteName").textContent = command
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

$("searchToastClose")?.addEventListener("click", () => {
    $("searchRecommendationToast")?.classList.add("hidden");
});
