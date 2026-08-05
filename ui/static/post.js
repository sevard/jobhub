const inputEl = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const messagesEl = document.getElementById("messages");
const messageTemplate = document.getElementById("message-template");
const API_BASE = "/api";

async function deleteMessage(id) {
    try {
        const response = await fetch(`${API_BASE}/delete_message/${id}`, { method: "DELETE" });
        if (!response.ok) {
            throw new Error("Unable to delete message");
        }

        const li = messagesEl.querySelector(`[data-id="${id}"]`);
        if (li) {
            li.remove();
        }

    } catch (error) {
        console.error(error);
    }
}

function buildMessageItem(id, text) {
    const fragment = messageTemplate.content.cloneNode(true);
    const li = fragment.querySelector("li");
    const span = fragment.querySelector(".message-content");
    const deleteBtn = fragment.querySelector(".delete-btn");

    li.dataset.id = id;
    span.textContent = text;
    deleteBtn.addEventListener("click", () => deleteMessage(id));
    return li;
}

async function submitMessage(text) {
    const response = await fetch(`${API_BASE}/post_message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: text }),
    });

    if (!response.ok) {
        throw new Error("Unable to save message");
    }

    const data = await response.json();
    messagesEl.prepend(buildMessageItem(data.id, text));
}

sendBtn.addEventListener("click", async () => {
    const value = inputEl.value.trim();
    if (!value) {
        return;
    }

    try {
        await submitMessage(value);
        inputEl.value = "";
    } catch (error) {
        console.error(error);
    }
});

async function loadMessageHistory() {
    try {
        const response = await fetch(`${API_BASE}/get_message?own_only=true`);
        const data = await response.json();
        const ownMessages = data.messages || [];
        for (const msg of ownMessages) {
            messagesEl.appendChild(buildMessageItem(msg.id, msg.content));
        }
    } catch (error) {
        console.error("Unable to load message history", error);
    }
}

loadMessageHistory();
