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

    const overlay = document.createElement("div");
    overlay.style.cssText =
        "position:fixed;inset:0;z-index:9999;background:rgba(15,23,42,.75);" +
        "display:flex;align-items:center;justify-content:center;padding:20px";
    overlay.innerHTML = `
        <div class="panel" style="max-width:520px;width:100%;margin:0">
            <h2>Connect to the Flask Backend</h2>
            <p>Enter the HTTPS Cloudflare Tunnel URL displayed on the lab laptop.</p>
            <label>Backend URL</label>
            <input id="apiBaseInput" type="url"
                   placeholder="https://example.trycloudflare.com"
                   style="width:100%;margin-bottom:12px">
            <p id="apiBaseError" style="color:#b00020"></p>
            <button id="apiBaseSave" type="button">Save and Connect</button>
        </div>`;
    document.body.appendChild(overlay);

    document.getElementById("apiBaseSave").addEventListener("click", () => {
        try {
            setApiBase(document.getElementById("apiBaseInput").value);
            location.reload();
        } catch (error) {
            document.getElementById("apiBaseError").textContent = error.message;
        }
    });
}

function renderNav(activePage) {
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
        <div class="wrapper">
            <aside class="sidebar">
                <div class="sidebar-header">
                    <div class="logo"><i class="fa-solid fa-robot"></i><span>NAO Classroom</span></div>
                </div>
                <nav>${nav}</nav>
            </aside>
            <div class="main">
                <header class="topbar">
                    <div><h1 id="staticPageTitle">NAO Classroom</h1>
                    <p>NAO Smart Classroom Monitoring System</p></div>
                    <div class="top-right">
                        <div id="clock">--:--:--</div>
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

    document.getElementById("changeApiBase").addEventListener("click", () => {
        const value = prompt("Enter the Flask HTTPS tunnel URL:", getApiBase());
        if (value === null) return;
        try {
            setApiBase(value);
            location.reload();
        } catch (error) {
            alert(error.message);
        }
    });

    setInterval(() => {
        const clock = document.getElementById("clock");
        if (clock) clock.textContent = new Date().toLocaleTimeString();
    }, 1000);
}

document.addEventListener("DOMContentLoaded", () => {
    ensureApiConfigured();
});
