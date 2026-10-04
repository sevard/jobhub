const formEl = document.getElementById("jobForm");
const pickupTimeInput = document.getElementById("pickupTimeInput");
const pickupLocationInput = document.getElementById("pickupLocationInput");
const dropoffLocationInput = document.getElementById("dropoffLocationInput");
const noteInput = document.getElementById("noteInput");
const messagesEl = document.getElementById("messages");
const messageTemplate = document.getElementById("message-template");
const API_BASE = "/api";

// Initialize Flatpickr for consistent cross-browser datetime picking
flatpickr("#pickupTimeInput", {
    enableTime: true,
    dateFormat: "Z", // We want the ISO timezone backend timestamp logic under the hood
    altInput: true,
    altFormat: "Y-m-d h:i K", // User facing explicit: 2026-08-12 12:00 PM
    minDate: "today"
});

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

function buildMessageItem(id, payload) {
    const fragment = messageTemplate.content.cloneNode(true);
    const li = fragment.querySelector("li");
    
    const timeEl = fragment.querySelector('[data-id="timeEl"]');
    const pickupEl = fragment.querySelector('[data-id="pickupEl"]');
    const dropoffEl = fragment.querySelector('[data-id="dropoffEl"]');
    const noteEl = fragment.querySelector('[data-id="noteEl"]');
    const deleteBtn = fragment.querySelector(".delete-btn");

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
        hours = hours ? hours : 12; 
        timeEl.textContent = `${yyyy}-${mm}-${dd} ${String(hours).padStart(2, '0')}:${mins} ${ampm}`;
    } else {
        timeEl.textContent = "TBD";
    }

    pickupEl.textContent = payload.pickup_location;
    dropoffEl.textContent = payload.dropoff_location;
    
    if (payload.note) {
        noteEl.textContent = `"${payload.note}"`;
    } else {
        noteEl.style.display = 'none';
    }
    
    deleteBtn.addEventListener("click", () => deleteMessage(id));

    // Remove the data-id attributes after cloning the template out
    timeEl.removeAttribute('data-id');
    pickupEl.removeAttribute('data-id');
    dropoffEl.removeAttribute('data-id');
    noteEl.removeAttribute('data-id');

    return li;
}

async function submitJob(payload) {
    const response = await fetch(`${API_BASE}/post_message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });

    if (!response.ok) {
        throw new Error("Unable to save message");
    }

    const data = await response.json();
    messagesEl.prepend(buildMessageItem(data.id, payload));
}

formEl.addEventListener("submit", async (e) => {
    e.preventDefault();
    
    const payload = {
        pickup_time: pickupTimeInput.value,
        pickup_location: pickupLocationInput.value.trim(),
        dropoff_location: dropoffLocationInput.value.trim(),
        note: noteInput.value.trim()
    };

    if (!payload.pickup_time || !payload.pickup_location || !payload.dropoff_location) {
        return;
    }

    try {
        await submitJob(payload);
        // Reset form
        pickupTimeInput.value = "";
        pickupLocationInput.value = "";
        dropoffLocationInput.value = "";
        noteInput.value = "";
    } catch (error) {
        console.error(error);
    }
});

// Clear button logic
const resetBtn = document.getElementById("resetBtn");
if (resetBtn) {
    resetBtn.addEventListener("click", () => {
        pickupTimeInput.value = "";
        pickupLocationInput.value = "";
        dropoffLocationInput.value = "";
        noteInput.value = "";
        // Optional flatpickr clear workaround if flatpickr holds onto value internally:
        if (pickupTimeInput._flatpickr) {
            pickupTimeInput._flatpickr.clear();
        }
    });
}

async function loadMessageHistory() {
    try {
        const response = await fetch(`${API_BASE}/get_message?own_only=true`);
        const data = await response.json();
        const ownMessages = data.messages || [];
        for (const msg of ownMessages) {
            messagesEl.appendChild(buildMessageItem(msg.id, msg));
        }
    } catch (error) {
        console.error("Unable to load message history", error);
    }
}

loadMessageHistory();
