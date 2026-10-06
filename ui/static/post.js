// Initialize Flatpickr for consistent cross-browser datetime picking
const pickupPicker = flatpickr("#pickupTimeInput", {
    enableTime: true,
    dateFormat: "Z", // We want the ISO timezone backend timestamp logic under the hood
    altInput: true,
    altFormat: "Y-m-d h:i K", // User facing explicit: 2026-08-12 12:00 PM
    minDate: "today",
    onReady: (selectedDates, dateStr, instance) => {
        // Flatpickr's calendar controls are generated without id/name
        const controls = {
            ".flatpickr-monthDropdown-months": "month",
            ".cur-year": "year",
            ".flatpickr-hour": "hour",
            ".flatpickr-minute": "minute",
        };
        for (const [selector, name] of Object.entries(controls)) {
            const el = instance.calendarContainer.querySelector(selector);
            if (el) {
                el.name = `pickup_time_${name}`;
                el.id = `pickupTime${name[0].toUpperCase()}${name.slice(1)}`;
            }
        }
    }
});

// Flatpickr's visible input is generated without id/name
pickupPicker.altInput.id = "pickupTimeDisplay";
pickupPicker.altInput.name = "pickup_time_display";
pickupPicker.altInput.setAttribute("aria-label", "Pickup Time");

// The reset button clears native inputs; also clear flatpickr
document.getElementById("jobForm").addEventListener("reset", () => pickupPicker.clear());
