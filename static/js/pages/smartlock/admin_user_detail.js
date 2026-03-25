document.addEventListener("DOMContentLoaded", function () {
  const script = document.getElementById("user-detail-script");
  const eventsUrl = script?.dataset.arduinoEventsUrl || "";
  const scanButtons = Array.from(document.querySelectorAll("[data-rfid-scan-button]"));
  const input = document.querySelector("[data-rfid-id-input]");
  const status = document.querySelector("[data-rfid-scan-status]");
  const enableInput = document.querySelector('input[name="rfid_enabled"]');

  if (!eventsUrl || !scanButtons.length || !input || !status) {
    return;
  }

  let baselineReady = false;
  let lastEventKey = "";
  let listening = false;
  let awaitingValidationResult = false;
  let pollInFlight = false;

  const eventKey = function (entry) {
    return [entry.timestamp || "", entry.kind || "", entry.line || ""].join("|");
  };

  const setListening = function (nextListening) {
    listening = nextListening;
    scanButtons.forEach(function (button) {
      button.textContent = nextListening ? "Listening..." : "Scan";
      button.classList.toggle("is-pending", nextListening);
    });
  };

  const setStatus = function (message, tone) {
    status.textContent = message;
    status.classList.remove("is-listening", "is-success", "is-error");
    if (tone) {
      status.classList.add(tone);
    }
  };

  const extractNewEntries = function (events) {
    if (!Array.isArray(events) || !events.length) {
      return [];
    }

    const newestKey = eventKey(events[events.length - 1]);
    if (!baselineReady) {
      baselineReady = true;
      lastEventKey = newestKey;
      return [];
    }

    let startIndex = events.findIndex(function (entry) {
      return eventKey(entry) === lastEventKey;
    });
    if (startIndex === -1) {
      startIndex = events.length - 1;
    }
    lastEventKey = newestKey;
    return events.slice(startIndex + 1);
  };

  const handleRfidRequest = function (value) {
    if (!value) {
      return;
    }
    const currentValue = input.value.trim();
    if (enableInput) {
      enableInput.checked = true;
    }
    setListening(false);
    if (currentValue && currentValue === value) {
      awaitingValidationResult = true;
      setStatus("Badge seen. Waiting for validation...", "is-listening");
      return;
    }
    awaitingValidationResult = false;
    input.value = value;
    setStatus("Badge captured. Save it, then scan again to validate it.", "is-success");
  };

  const handleRfidResult = function (decision, detail) {
    if (!awaitingValidationResult) {
      return;
    }
    awaitingValidationResult = false;
    if (decision === "ALLOW") {
      setStatus((detail || "RFID badge valid") + " RFID badge valid.", "is-success");
      return;
    }
    if (decision === "DENY") {
      const suffix = detail ? ": " + detail : ".";
      setStatus("RFID badge denied" + suffix, "is-error");
    }
  };

  const handleEntries = function (entries) {
    entries.forEach(function (entry) {
      const line = entry.line || "";
      if (entry.kind === "arduino_rx" && line.startsWith("CHECK|rfid|")) {
        const parts = line.split("|", 3);
        const badgeValue = (parts[2] || "").trim();
        if (listening) {
          handleRfidRequest(badgeValue);
        }
        return;
      }

      if (entry.kind === "arduino_tx" && line.startsWith("RESULT|")) {
        const parts = line.split("|");
        const decision = (parts[1] || "").trim();
        const detail = parts.slice(2).join("|").trim();
        handleRfidResult(decision, detail);
      }
    });
  };

  const loadEvents = async function () {
    if (pollInFlight) {
      return;
    }
    pollInFlight = true;
    try {
      const response = await window.fetch(eventsUrl + "?limit=200", {
        credentials: "same-origin",
        cache: "no-store"
      });
      if (!response.ok) {
        throw new Error("Request failed with " + response.status);
      }
      const payload = await response.json();
      handleEntries(extractNewEntries(payload.events || []));
    } catch (error) {
      setListening(false);
      awaitingValidationResult = false;
      setStatus("RFID scanner unavailable: " + error.message, "is-error");
    } finally {
      pollInFlight = false;
    }
  };

  scanButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      if (listening) {
        setListening(false);
        awaitingValidationResult = false;
        setStatus("Scan cancelled.", "");
        return;
      }
      setListening(true);
      awaitingValidationResult = false;
      setStatus("Waiting for RFID badge...", "is-listening");
      loadEvents();
    });
  });

  loadEvents();
  window.setInterval(loadEvents, 1500);
});
