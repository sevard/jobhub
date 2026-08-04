const inputEl = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const messagesEl = document.getElementById("messages");
const API_BASE = "";

const authoredMessages = [];

function renderMessages() {
    messagesEl.innerHTML = "";
    authoredMessages.forEach((msg) => {
        const li = document.createElement("li");
        li.className = "d-flex justify-content-between align-items-center gap-2";
        li.dataset.id = msg.id;

        const span = document.createElement("span");
        span.textContent = msg.content;
        li.appendChild(span);

        const deleteBtn = document.createElement("button");
        deleteBtn.type = "button";
        deleteBtn.className = "btn btn-sm btn-outline-danger";
        deleteBtn.textContent = "Delete";
        deleteBtn.addEventListener("click", () => deleteMessage(msg.id));
        li.appendChild(deleteBtn);

        messagesEl.appendChild(li);
    });
}

function addMessage(id, text) {
    authoredMessages.unshift({ id, content: text });
    renderMessages();
}

async function deleteMessage(id) {
    try {
        const response = await fetch(`${API_BASE}/delete_message/${id}`, { method: "DELETE" });
        if (!response.ok) {
            throw new Error("Unable to delete message");
        }
        const index = authoredMessages.findIndex((msg) => msg.id === id);
        if (index !== -1) {
            authoredMessages.splice(index, 1);
            renderMessages();
        }
    } catch (error) {
        console.error(error);
    }
}

async function loadMessageHistory() {
    try {
        const response = await fetch(`${API_BASE}/get_message`);
        const data = await response.json();
        // list_messages returns newest first, matching how authoredMessages is ordered
        authoredMessages.push(...(data.messages || []));
        renderMessages();
    } catch (error) {
        console.error("Unable to load message history", error);
    }
}

async function postMessage(text) {
    const response = await fetch(`${API_BASE}/post_message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: text }),
    });

    if (!response.ok) {
        throw new Error("Unable to save message");
    }

    const data = await response.json();
    addMessage(data.id, text);
}

sendBtn.addEventListener("click", async () => {
    const value = inputEl.value.trim();
    if (!value) {
        return;
    }

    try {
        await postMessage(value);
        inputEl.value = "";
    } catch (error) {
        console.error(error);
    }
});

loadMessageHistory();
