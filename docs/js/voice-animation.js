const VOICE_ANIMATION_KEY = "nao_voice_animation_enabled";
function voiceAnimationEnabled() { return localStorage.getItem(VOICE_ANIMATION_KEY) !== "false"; }
function updateAnimationToggle(button, enabled) {
    if (!button) return;
    button.setAttribute("aria-pressed", String(enabled));
    button.classList.toggle("is-on", enabled);
    const label = button.querySelector("[data-animation-label]");
    if (label) label.textContent = enabled ? "Animation On" : "Animation Off";
}
function initVoiceAnimationToggle(buttonId) {
    const button = document.getElementById(buttonId);
    if (!button) return;
    const heading = button.closest(".voice-panel-heading");
    const errorMessage = heading?.querySelector(".animation-toggle-error");
    const showError = (message) => {
        if (!errorMessage) return;
        errorMessage.textContent = message || "Could not update speech animation.";
        errorMessage.classList.add("visible");
    };
    const clearError = () => {
        if (!errorMessage) return;
        errorMessage.textContent = "";
        errorMessage.classList.remove("visible");
    };
    const apply = (enabled) => {
        localStorage.setItem(VOICE_ANIMATION_KEY, String(enabled));
        updateAnimationToggle(button, enabled);
        window.dispatchEvent(new CustomEvent("voice-animation-changed", {detail: {enabled}}));
    };
    button.addEventListener("click", async () => {
        const previousEnabled = voiceAnimationEnabled();
        const enabled = !previousEnabled;
        apply(enabled);
        clearError();
        button.disabled = true;
        try {
            const result = await apiFetch("/api/voice/animation", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({enabled})});
            apply(result.enabled !== false);
        } catch (error) {
            apply(previousEnabled);
            showError(error.message);
            console.warn("Could not update robot animation setting: Animation update request fails.", error);
        } finally {
            button.disabled = false;
        }
    });
    updateAnimationToggle(button, voiceAnimationEnabled());
    apiFetch("/api/voice/animation")
        .then((result) => {
            clearError();
            apply(result.enabled !== false);
        })
        .catch((error) => showError(error.message));
}
