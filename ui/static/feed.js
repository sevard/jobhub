const messagesEl = document.getElementById("messages");
const emptyEl = document.getElementById("empty-state");
const messageTemplate = document.getElementById("message-template");
const API_BASE = "/api";

function formatPickupTime(value) {
    const d = new Date(value);
    if (!value || Number.isNaN(d.getTime())) return "TBD";
    return d.toLocaleString([], {
        year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit",
    });
}

function updateEmptyState() {
    emptyEl.hidden = messagesEl.children.length > 0;
}

function buildMessageItem(id, payload) {
    const fragment = messageTemplate.content.cloneNode(true);
    const li = fragment.querySelector("li");
    const field = (name) => fragment.querySelector(`[data-field="${name}"]`);

    li.dataset.id = id;
    field("time").textContent = formatPickupTime(payload.pickup_time);
    field("pickup").textContent = payload.pickup_location || "TBD";
    field("dropoff").textContent = payload.dropoff_location || "TBD";

    const noteEl = field("note");
    if (payload.note) {
        noteEl.textContent = `"${payload.note}"`;
    } else {
        noteEl.hidden = true;
    }

    return li;
}

function hasMessage(id) {
    return messagesEl.querySelector(`[data-id="${id}"]`) !== null;
}

function addMessage(payload, { prepend = false } = {}) {
    if (hasMessage(payload.id)) return;
    const li = buildMessageItem(payload.id, payload);
    if (prepend) {
        messagesEl.prepend(li);
    } else {
        messagesEl.appendChild(li);
    }
    updateEmptyState();
}

function removeMessage(id) {
    const li = messagesEl.querySelector(`[data-id="${id}"]`);
    if (li) {
        li.remove();
        updateEmptyState();
    }
}

// Replaces the list with the server's current jobs, so it also repairs anything missed while disconnected.
async function loadMessageHistory() {
    try {
        const response = await fetch(`${API_BASE}/get_jobs`, { cache: "no-store" });
        if (response.status === 401) {
            window.location.href = "/account";
            return;
        }
        if (!response.ok) {
            console.error("Unable to load jobs", response.status);
            return;
        }
        const data = await response.json();
        messagesEl.replaceChildren();
        // list_jobs returns newest first; append in that order to keep newest on top
        for (const msg of data.messages || []) {
            addMessage(msg);
        }
        updateEmptyState();
    } catch (error) {
        console.error("Unable to load job history", error);
    }
}

function handleLiveEvent(data) {
    let payload;
    try {
        payload = JSON.parse(data);
    } catch (error) {
        console.error("Received unparseable job payload, skipping", data);
        return;
    }

    if (payload.type === "delete") {
        removeMessage(payload.id);
    } else {
        addMessage(payload, { prepend: true });
    }
}

let reconnectDelay = 1000;

function connectWebSocket() {
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${scheme}//${location.host}/ws`);
    socket.onopen = () => {
        reconnectDelay = 1000;
        loadMessageHistory();
    };
    socket.onmessage = (event) => handleLiveEvent(event.data);
    socket.onclose = (event) => {
        loadMessageHistory();
        if (event.code === 1008) {
            return;
        }
        setTimeout(connectWebSocket, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, 30000);
    };
}

// A page restored from the back/forward cache keeps stale state and a dead stream.
window.addEventListener("pageshow", (event) => {
    if (event.persisted) location.reload();
});

connectWebSocket();
