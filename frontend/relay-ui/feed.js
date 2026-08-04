const messagesEl = document.getElementById("messages");
const API_BASE = "";
// The WebSocket URL is constructed based on the current page's protocol and host.
const WS_URL = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;

function addMessage(id, text) {
    const li = document.createElement("li");
    li.dataset.id = id;
    li.textContent = text;
    messagesEl.prepend(li);
}

function removeMessage(id) {
    const li = messagesEl.querySelector(`[data-id="${id}"]`);
    if (li) { 
        li.remove();
    }
}

async function loadMessageHistory() {
    try {
        const response = await fetch(`${API_BASE}/get_message`);
        const data = await response.json();
        // list_messages returns newest first
        // append in that order to keep newest on top
        (data.messages || []).forEach((msg) => {
            const li = document.createElement("li");
            li.dataset.id = msg.id;
            li.textContent = msg.content;
            messagesEl.appendChild(li);
        });
    } catch (error) {
        console.error("Unable to load message history", error);
    }
}

function connectLiveFeed() {
    const ws = new WebSocket(WS_URL);
    ws.onmessage = (event) => {
        let payload;
        try {
            payload = JSON.parse(event.data);
        } catch (error) {
            addMessage(undefined, event.data);
            return;
        }

        if (payload.type === "delete") {
            removeMessage(payload.id);
        } else {
            addMessage(payload.id, payload.content);
        }
    };
}

loadMessageHistory().then(connectLiveFeed);
