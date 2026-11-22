const NAO_API_STORAGE_KEY = "nao_api_base";

function getApiBase() {
    const value = (localStorage.getItem(NAO_API_STORAGE_KEY) || "").replace(/\/+$/, "");
    return /^https:\/\//i.test(value) ? value : "";
}

function setApiBase(value) {
    value = String(value || "").trim().replace(/\/+$/, "");
    if (!value) {
        localStorage.removeItem(NAO_API_STORAGE_KEY);
        return;
    }

    if (!/^https:\/\//i.test(value)) {
        throw new Error("Enter the HTTPS Cloudflare Tunnel URL beginning with https://");
    }

    localStorage.setItem(NAO_API_STORAGE_KEY, value);
}

function apiUrl(path) {
    const base = getApiBase();
    if (!base) {
        throw new Error("Backend URL is not configured.");
    }
    return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}

async function apiFetch(path, options = {}) {
    let response;
    try {
        response = await fetch(apiUrl(path), options);
    } catch (error) {
        throw new Error(
            "Failed to reach the Flask backend. Start Flask and Cloudflare Tunnel, " +
            "then update the backend URL in Settings."
        );
    }
    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json")
        ? await response.json()
        : await response.text();

    if (!response.ok) {
        const message = typeof data === "object"
            ? data.message || "Request failed."
            : data || "Request failed.";
        throw new Error(message);
    }
    return data;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function ensureApiConfigured() {
    if (getApiBase()) return;

    const modal = document.getElementById("apiBaseModal");
    const input = document.getElementById("apiBaseInput");
    if (!modal || !input) return;

    input.value = getApiBase();
    modal.classList.remove("hidden");
    input.focus();
}

window.processingOverlay = {
    show(title = "Loading", message = "Please wait while processing...") {
        const overlay = document.getElementById("processingOverlay");
        if (!overlay) return;
        document.getElementById("processingTitle").textContent = title;
        document.getElementById("processingMessage").textContent = message;
        overlay.classList.add("visible");
        overlay.setAttribute("aria-hidden", "false");
    },
    hide() {
        const overlay = document.getElementById("processingOverlay");
        if (!overlay) return;
        overlay.classList.remove("visible");
        overlay.setAttribute("aria-hidden", "true");
    }
};

function renderNav(activePage) {
    if (!document.querySelector('script[src*="gsap"]')) {
        const gsapScript = document.createElement("script");
        gsapScript.src = "https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js";
        gsapScript.defer = true;
        document.head.appendChild(gsapScript);
    }
    const navItems = [
        ["index.html", "house", "Dashboard"],
        ["voice.html", "microphone-lines", "Voice Recognition"],
        ["vision.html", "camera", "Vision Monitoring"],
        ["attendance.html", "user-check", "Attendance"],
        ["behaviour.html", "eye", "Behaviour Analysis"],
        ["subjects.html", "book", "Subjects"],
        ["students.html", "user-graduate", "Students"],
        ["reports.html", "chart-line", "Reports"],
        ["settings.html", "gear", "Settings"],
    ];

    const nav = navItems.map(([file, icon, label]) => `
        <a class="${file === activePage ? "active" : ""}" href="${file}">
            <i class="fa-solid fa-${icon}"></i><span>${label}</span>
        </a>
    `).join("");

    document.body.insertAdjacentHTML("afterbegin", `
        <div id="processingOverlay" class="processing-overlay" aria-live="polite" aria-hidden="true">
            <div class="processing-card">
                <div class="processing-spinner"></div>
                <strong id="processingTitle">Loading</strong>
                <span id="processingMessage">Please wait while the page is processing...</span>
            </div>
        </div>
        <div id="apiBaseModal" class="api-base-modal hidden" role="dialog" aria-modal="true" aria-labelledby="apiBaseTitle">
            <div class="api-base-card">
                <div class="api-base-header">
                    <div>
                        <h2 id="apiBaseTitle">Connect to Flask Backend</h2>
                        <p>Enter the HTTPS Cloudflare Tunnel URL for the Flask backend.</p>
                    </div>
                    <button id="apiBaseClose" class="api-base-close" type="button" aria-label="Close">
                        <i class="fa-solid fa-xmark"></i>
                    </button>
                </div>
                <label for="apiBaseInput">Backend URL</label>
                <input id="apiBaseInput" type="url" placeholder="https://example.trycloudflare.com" autocomplete="url">
                <p id="apiBaseError" class="api-base-error" aria-live="polite"></p>
                <div class="api-base-actions">
                    <button id="apiBaseCancel" class="api-base-cancel" type="button">Cancel</button>
                    <button id="apiBaseSave" class="api-base-save" type="button">Save and Connect</button>
                </div>
            </div>
        </div>
        <div class="wrapper">
            <aside class="sidebar">
                <div class="sidebar-header">
                    <div class="logo">
                        <button id="logoToggleBtn" class="logo-mark-button" type="button" aria-label="Expand navigation" title="Expand navigation">
                            <i class="fa-solid fa-robot"></i>
                        </button>
                        <span class="logo-copy">NAO Classroom</span>
                    </div>
                    <button id="toggleBtn" type="button" aria-label="Collapse navigation" title="Collapse navigation">
                        <svg class="panel-toggle-icon" viewBox="0 0 24 24" aria-hidden="true">
                            <rect x="3" y="3" width="18" height="18" rx="2"></rect>
                            <path d="m9 15-3-3 3-3"></path>
                            <path d="M14 8v8"></path>
                        </svg>
                    </button>
                </div>
                <nav>${nav}</nav>
            </aside>
            <div class="main">
                <header class="topbar">
                    <div><h1 id="staticPageTitle">NAO Classroom</h1>
                    <p>NAO Smart Classroom Monitoring System</p></div>
                    <div class="top-right">
                        <div id="clock">--:--:--</div>
                        <button id="mobileMenuBtn" class="mobile-menu-btn" type="button"
                                aria-label="Open navigation" aria-controls="sidebar" aria-expanded="false">
                            <i class="fa-solid fa-bars"></i>
                        </button>
                        <div id="robotStatusPill" class="robot-pill disconnected">
                            <span id="robotStatusDot" class="dot"></span>
                            <span id="robotStatusText">Checking Robot</span>
                        </div>
                        <button id="changeApiBase" type="button">Change Backend</button>
                    </div>
                </header>
                <main class="content" id="pageContent"></main>
            </div>
        </div>
    `);

    const content = document.getElementById("pageContent");
    const source = document.querySelector("template#pageTemplate");
    if (source) content.appendChild(source.content.cloneNode(true));

        const sidebar = document.querySelector(".sidebar");
        const toggleBtn = document.getElementById("toggleBtn");
        const logoToggleBtn = document.getElementById("logoToggleBtn");
        const mobileMenuBtn = document.getElementById("mobileMenuBtn");
        const mobileQuery = window.matchMedia("(max-width: 576px)");
        let sidebarBackdrop = document.querySelector(".sidebar-backdrop");

        if (!sidebarBackdrop) {
            sidebarBackdrop = document.createElement("div");
            sidebarBackdrop.className = "sidebar-backdrop";
            sidebarBackdrop.setAttribute("aria-hidden", "true");
            document.body.appendChild(sidebarBackdrop);
        }

        if (sidebar && toggleBtn) {
            const setMobileSidebar = (open) => {
                sidebar.classList.toggle("open", open);
                sidebarBackdrop.classList.toggle("visible", open);
                mobileMenuBtn?.setAttribute("aria-expanded", String(open));
                mobileMenuBtn?.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
                document.body.classList.toggle("sidebar-open", open);
            };

            const syncInitialSidebar = () => {
                if (mobileQuery.matches) {
                    sidebar.classList.remove("collapsed");
                    setMobileSidebar(false);
                    toggleBtn.style.display = "flex";
                } else {
                    sidebar.classList.remove("open");
                    sidebarBackdrop.classList.remove("visible");
                    document.body.classList.remove("sidebar-open");
                    const collapsed = localStorage.getItem("docsSidebarCollapsed") === "true";
                    sidebar.classList.toggle("collapsed", collapsed);
                    toggleBtn.style.display = collapsed ? "none" : "flex";
                }
            };

            const updateToggleLabel = () => {
                const collapsed = sidebar.classList.contains("collapsed");
                const label = collapsed ? "Expand navigation" : "Collapse navigation";
                toggleBtn.setAttribute("aria-label", label);
                toggleBtn.setAttribute("title", label);
                toggleBtn.style.display = collapsed ? "none" : "flex";
            };

            syncInitialSidebar();
            mobileQuery.addEventListener("change", syncInitialSidebar);

            const toggleSidebar = () => {
                if (mobileQuery.matches) {
                    setMobileSidebar(!sidebar.classList.contains("open"));
                    return;
                }
                const collapsed = sidebar.classList.toggle("collapsed");
                localStorage.setItem("docsSidebarCollapsed", String(collapsed));
                updateToggleLabel();
            };

            toggleBtn.addEventListener("click", toggleSidebar);
            mobileMenuBtn?.addEventListener("click", () => setMobileSidebar(!sidebar.classList.contains("open")));
            logoToggleBtn?.addEventListener("click", () => {
                if (sidebar.classList.contains("collapsed")) toggleSidebar();
                else if (mobileQuery.matches) setMobileSidebar(true);
            });
            sidebarBackdrop.addEventListener("click", () => setMobileSidebar(false));
            document.querySelectorAll(".sidebar nav a").forEach(link => {
                link.addEventListener("click", () => {
                    if (mobileQuery.matches) setMobileSidebar(false);
                });
            });
            document.addEventListener("keydown", event => {
                if (event.key === "Escape" && mobileQuery.matches) setMobileSidebar(false);
            });
        }

    const apiBaseModal = document.getElementById("apiBaseModal");
    const apiBaseInput = document.getElementById("apiBaseInput");
    const apiBaseError = document.getElementById("apiBaseError");

    const closeApiBaseModal = () => {
        apiBaseModal.classList.add("hidden");
        apiBaseError.textContent = "";
    };

    document.getElementById("changeApiBase").addEventListener("click", () => {
        apiBaseInput.value = getApiBase();
        apiBaseError.textContent = "";
        apiBaseModal.classList.remove("hidden");
        apiBaseInput.focus();
    });

    document.getElementById("apiBaseClose").addEventListener("click", closeApiBaseModal);
    document.getElementById("apiBaseCancel").addEventListener("click", closeApiBaseModal);
    apiBaseModal.addEventListener("click", (event) => {
        if (event.target === apiBaseModal) closeApiBaseModal();
    });
    apiBaseInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") document.getElementById("apiBaseSave").click();
        if (event.key === "Escape") closeApiBaseModal();
    });
    document.getElementById("apiBaseSave").addEventListener("click", () => {
        try {
            setApiBase(apiBaseInput.value);
            location.reload();
        } catch (error) {
            apiBaseError.textContent = error.message;
        }
    });

    document.querySelectorAll(".sidebar nav a").forEach(link => {
        link.addEventListener("click", () => {
            if (link.href && link.href !== window.location.href) {
                window.processingOverlay.show("Opening Page", "Loading the next page...");
            }
        });
    });

    setInterval(() => {
        const clock = document.getElementById("clock");
        if (clock) clock.textContent = new Date().toLocaleTimeString();
    }, 1000);

    window.processingOverlay.show("Loading Page", "Preparing the page...");
}

async function updateRobotStatus() {
    const pill = document.getElementById("robotStatusPill");
    const text = document.getElementById("robotStatusText");
    if (!pill || !text) return;

    if (!getApiBase()) {
        pill.classList.remove("connected");
        pill.classList.add("disconnected");
        text.textContent = "Robot Offline";
        return;
    }

    try {
        const data = await apiFetch("/api/ping?t=" + Date.now());
        const status = data.status || data;
        const connected = Boolean(data.connected ?? status.connected);

        pill.classList.toggle("connected", connected);
        pill.classList.toggle("disconnected", !connected);
        text.textContent = connected ? "Robot Connected" : "Robot Offline";
    } catch (error) {
        pill.classList.remove("connected");
        pill.classList.add("disconnected");
        text.textContent = "Robot Unavailable";
    }
}

document.addEventListener("DOMContentLoaded", () => {
    ensureApiConfigured();
    updateRobotStatus();
    setInterval(updateRobotStatus, 3000);
});

window.addEventListener("load", () => {
    window.processingOverlay.hide();
    if (window.gsap) {
        gsap.from(".content > *", {
            opacity: 0,
            y: 14,
            duration: 0.45,
            stagger: 0.07,
            ease: "power2.out"
        });
        gsap.from(".stat", {
            opacity: 0,
            y: 10,
            duration: 0.35,
            stagger: 0.05,
            ease: "power2.out",
            delay: 0.08
        });
    }
});

const nativeFetch = window.fetch.bind(window);
window.fetch = async function (...args) {
    const options = args[1] || {};
    const method = String(options.method || "GET").toUpperCase();
    let mutationOverlayShown = false;

    if (method !== "GET" && method !== "HEAD") {
        window.processingOverlay.show(
            "Processing",
            "Please wait while changes are being saved..."
        );
        mutationOverlayShown = true;
    }

    try {
        return await nativeFetch(...args);
    } finally {
        if (mutationOverlayShown) {
            setTimeout(() => window.processingOverlay.hide(), 300);
        }
    }
};
