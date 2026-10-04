const formEl = document.getElementById("authForm");
const usernameInput = document.getElementById("usernameInput");
const passwordInput = document.getElementById("passwordInput");
const errorEl = document.getElementById("authError");
const submitBtn = document.getElementById("submitBtn");
const modeHint = document.getElementById("modeHint");
const switchText = document.getElementById("switchText");
const switchLink = document.getElementById("switchLink");
const roleGroup = document.getElementById("roleGroup");
const roleSelect = document.getElementById("roleSelect");

let mode = "login";

function setMode(next) {
    mode = next;
    const signup = mode === "signup";
    submitBtn.textContent = signup ? "Sign up" : "Log in";
    modeHint.textContent = signup ? "Create your account." : "Log in to your account.";
    switchText.textContent = signup ? "Already have an account?" : "No account yet?";
    switchLink.textContent = signup ? "Log in" : "Sign up";
    passwordInput.autocomplete = signup ? "new-password" : "current-password";
    roleGroup.hidden = !signup;
    errorEl.textContent = "";
}

switchLink.addEventListener("click", (event) => {
    event.preventDefault();
    setMode(mode === "login" ? "signup" : "login");
});

formEl.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorEl.textContent = "";
    if (!formEl.checkValidity()) {
        errorEl.textContent = "Enter a valid username and a password of at least 8 characters.";
        return;
    }

    submitBtn.disabled = true;
    try {
        const response = await fetch(`/api/${mode}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                username: usernameInput.value.trim(),
                password: passwordInput.value,
                ...(mode === "signup" && { role: roleSelect.value })
            })
        });
        if (response.ok) {
            window.location.href = "/account/home";
            return;
        }
        const data = await response.json().catch(() => ({}));
        errorEl.textContent = typeof data.detail === "string"
            ? data.detail
            : "Check your username and password and try again.";
    } catch (error) {
        errorEl.textContent = "Could not reach the server.";
    } finally {
        submitBtn.disabled = false;
    }
});
