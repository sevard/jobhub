const messagesEl = document.getElementById("messages");
const messageTemplate = document.getElementById("message-template");
const API_BASE = "/api";

// The WebSocket URL is constructed based on the current page's protocol and host.
const WS_URL = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;

function buildMessageItem(id, payload) {
    const fragment = messageTemplate.content.cloneNode(true);
    const li = fragment.querySelector("li");
    
    const timeEl = fragment.querySelector('[data-id="timeEl"]');
    const pickupEl = fragment.querySelector('[data-id="pickupEl"]');
    const dropoffEl = fragment.querySelector('[data-id="dropoffEl"]');
    const noteEl = fragment.querySelector('[data-id="noteEl"]');

    li.dataset.id = id;
    
    // Format the date securely like 2026-08-12 12:00 PM
    if (payload.pickup_time) {
        const d = new Date(payload.pickup_time);
        const yyyy = d.getFullYear();
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        let hours = d.getHours();
        const mins = String(d.getMinutes()).padStart(2, '0');
        const ampm = hours >= 12 ? 'PM' : 'AM';
        hours = hours % 12;
        hours = hours ? hours : 12; // the hour '0' should be '12'
        timeEl.textContent = `${yyyy}-${mm}-${dd} ${String(hours).padStart(2, '0')}:${mins} ${ampm}`;
    } else {
        timeEl.textContent = "TBD";
    }

    pickupEl.textContent = payload.pickup_location || "TBD";
    dropoffEl.textContent = payload.dropoff_location || "TBD";
    
    if (payload.note) {
        noteEl.textContent = `"${payload.note}"`;
    } else {
        noteEl.style.display = 'none';
    }

    // Need to remove data-id attributes after cloning to keep it clean (optional, but consistent with prior behavior)
    timeEl.removeAttribute('data-id');
    pickupEl.removeAttribute('data-id');
    dropoffEl.removeAttribute('data-id');
    noteEl.removeAttribute('data-id');

    return li;
}

async function loadMessageHistory() {
    try {
        const response = await fetch(`${API_BASE}/get_message`);
        const data = await response.json();
        const messages = data.messages || [];
        // list_messages returns newest first; append in that order to keep newest on top
        for (const msg of messages) {
            messagesEl.appendChild(buildMessageItem(msg.id, msg));
        }
    } catch (error) {
        console.error("Unable to load message history", error);
    }
}

function removeMessage(id) {
    const li = messagesEl.querySelector(`[data-id="${id}"]`);
    if (li) { 
        li.remove();
    }
}

function connectLiveFeed() {
    const ws = new WebSocket(WS_URL);
    ws.onmessage = (event) => {
        let payload;
        try {
            payload = JSON.parse(event.data);
        } catch (error) {
            console.error("Received raw string or unparseable job ws payload, skipping!", event.data);
            return;
        }

        if (payload.type === "delete") {
            removeMessage(payload.id);
        } else {
            messagesEl.prepend(buildMessageItem(payload.id, payload));
        }
    };
}

loadMessageHistory().then(connectLiveFeed);
