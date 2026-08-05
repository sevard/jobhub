const messagesEl = document.getElementById("messages");
const messageTemplate = document.getElementById("message-template");
const API_BASE = "/api";

// The WebSocket URL is constructed based on the current page's protocol and host.
const WS_URL = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;

function buildMessageItem(id, text) {
    const fragment = messageTemplate.content.cloneNode(true);
    const li = fragment.querySelector("li");
    const link = fragment.querySelector("a.message-link");
    li.dataset.id = id;
    link.href = `#message-${id}`;
    link.textContent = text;
    return li;
}

async function loadMessageHistory() {
    try {
        const response = await fetch(`${API_BASE}/get_message`);
        const data = await response.json();
        const messages = data.messages || [];
        // list_messages returns newest first; append in that order to keep newest on top
        for (const msg of messages) {
            messagesEl.appendChild(buildMessageItem(msg.id, msg.content));
        }
    } catch (error) {
        console.error("Unable to load message history", error);
    }
}

function addMessage(id, text) {
    messagesEl.prepend(buildMessageItem(id, text));
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
