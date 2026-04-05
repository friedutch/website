document.addEventListener("DOMContentLoaded", function () {
  const script = document.getElementById("admin-panel-script");
  const cooldownRemaining = Number(script?.dataset.cooldownRemaining || "0");
  const arduinoEventsUrl = script?.dataset.arduinoEventsUrl || "";
  const tabs = Array.from(document.querySelectorAll("[data-panel-tab]"));
  const sections = Array.from(document.querySelectorAll("[data-panel-section]"));
  const tabStorageKey = "smartlock-admin-active-tab";
  const storage = window.friedutchStorage || {
    get: function (key) {
      try {
        return window.localStorage.getItem(key);
      } catch (error) {
        return null;
      }
    },
    set: function (key, value) {
      try {
        window.localStorage.setItem(key, value);
      } catch (error) {
        // Ignore storage failures and keep the UI working.
      }
    }
  };

  const activateTab = function (name) {
    const tabExists = tabs.some(function (tab) { return tab.dataset.panelTab === name; });
    const nextTab = tabExists ? name : "people";
    tabs.forEach(function (tab) {
      const isActive = tab.dataset.panelTab === nextTab;
      tab.classList.toggle("active", isActive);
      tab.setAttribute("aria-selected", isActive ? "true" : "false");
    });
    sections.forEach(function (section) {
      section.classList.toggle("active", section.dataset.panelSection === nextTab);
    });
    storage.set(tabStorageKey, nextTab);
  };

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      activateTab(tab.dataset.panelTab);
    });
  });

  if (tabs.length && sections.length) {
    let initialTab = storage.get(tabStorageKey) || "people";
    if (initialTab === "settings") {
      initialTab = "people";
    }
    activateTab(initialTab);
  }

  const userSearchInput = document.getElementById("user-search");
  const userCards = Array.from(document.querySelectorAll("[data-user-card]"));
  const userSearchEmpty = document.getElementById("user-search-empty");
  const logSearchInput = document.getElementById("log-search");
  const logCards = Array.from(document.querySelectorAll("[data-log-card]"));
  const logSearchEmpty = document.getElementById("log-search-empty");
  const copyJoinUrlButton = document.querySelector(".copy-join-url-btn");
  const joinInviteTimer = document.getElementById("join-invite-timer");
  const arduinoConsole = document.getElementById("arduino-console");
  const arduinoRefreshButton = document.getElementById("arduino-refresh");
  let arduinoPollInFlight = false;
  let arduinoLastRendered = "";
  const syncCreateCardHeights = function () {
    document.querySelectorAll("[data-create-card]").forEach(function (card) {
      const group = card.dataset.createCard;
      const sources = Array.from(document.querySelectorAll('[data-size-source="' + group + '"]')).filter(function (source) {
        return source.style.display !== "none";
      });
      card.style.minHeight = "";
      if (!sources.length) {
        return;
      }
      let maxHeight = 0;
      sources.forEach(function (source) {
        maxHeight = Math.max(maxHeight, source.offsetHeight);
      });
      if (maxHeight > 0) {
        card.style.minHeight = maxHeight + "px";
      }
    });
  };

  if (logSearchInput && logCards.length) {
    const filterLogs = function () {
      const query = logSearchInput.value.trim().toLowerCase();
      let visibleCount = 0;
      logCards.forEach(function (card) {
        const haystack = card.dataset.logSearch || "";
        const visible = !query || haystack.includes(query);
        card.style.display = visible ? "" : "none";
        if (visible) {
          visibleCount += 1;
        }
      });
      if (logSearchEmpty) {
        logSearchEmpty.classList.toggle("user-search-empty-hidden", visibleCount > 0);
      }
      syncCreateCardHeights();
    };
    logSearchInput.addEventListener("input", filterLogs);
    filterLogs();
  }

  if (copyJoinUrlButton) {
    copyJoinUrlButton.addEventListener("click", async function () {
      await navigator.clipboard.writeText(copyJoinUrlButton.dataset.copyText || "");
      copyJoinUrlButton.textContent = "Copied";
    });
  }

  if (joinInviteTimer) {
    let remaining = Number(joinInviteTimer.dataset.remaining || "0");
    const tickJoinInvite = function () {
      if (remaining <= 0) {
        joinInviteTimer.textContent = "expired";
        clearInterval(joinInviteIntervalId);
        return;
      }
      joinInviteTimer.textContent = Math.floor(remaining / 60) + ":" + String(remaining % 60).padStart(2, "0");
      remaining -= 1;
    };
    tickJoinInvite();
    var joinInviteIntervalId = setInterval(tickJoinInvite, 1000);
  }

  const renderArduinoEvents = function (events) {
    if (!arduinoConsole) {
      return;
    }
    if (!Array.isArray(events) || !events.length) {
      const emptyState = "Waiting for Arduino events...";
      if (arduinoLastRendered !== emptyState) {
        arduinoConsole.textContent = emptyState;
        arduinoLastRendered = emptyState;
      }
      return;
    }
    const lines = events.map(function (entry) {
      const timestamp = entry.timestamp || "unknown-time";
      const kind = entry.kind || "event";
      const line = entry.line || "";
      return "[" + timestamp + "] " + kind + " " + line;
    }).join("\n");
    if (arduinoLastRendered === lines) {
      return;
    }
    arduinoConsole.textContent = lines;
    arduinoConsole.scrollTop = arduinoConsole.scrollHeight;
    arduinoLastRendered = lines;
  };

  const loadArduinoEvents = async function () {
    if (!arduinoEventsUrl || !arduinoConsole || arduinoPollInFlight) {
      return;
    }
    arduinoPollInFlight = true;
    try {
      const response = await window.fetch(arduinoEventsUrl + "?limit=200", {
        credentials: "same-origin",
        cache: "no-store"
      });
      if (!response.ok) {
        throw new Error("Request failed with " + response.status);
      }
      const payload = await response.json();
      renderArduinoEvents(payload.events || []);
    } catch (error) {
      arduinoConsole.textContent = "Arduino console unavailable: " + error.message;
    } finally {
      arduinoPollInFlight = false;
    }
  };

  if (arduinoRefreshButton) {
    arduinoRefreshButton.addEventListener("click", function () {
      loadArduinoEvents();
    });
  }

  if (arduinoConsole && arduinoEventsUrl) {
    loadArduinoEvents();
    setInterval(loadArduinoEvents, 2000);
  }

  const emailChangeToggle = document.querySelector("[data-email-change-open]");
  const emailChangeForm = document.querySelector("[data-email-change-form]");
  const emailChangeCancel = document.querySelector("[data-email-change-cancel]");
  const emailChangeInput = document.querySelector("[data-email-change-input]");

  const setEmailChangeExpanded = function (expanded) {
    if (emailChangeToggle) {
      emailChangeToggle.classList.toggle("email-change-toggle-hidden", expanded);
    }
    if (emailChangeForm) {
      emailChangeForm.classList.toggle("email-change-form-hidden", !expanded);
    }
    if (expanded && emailChangeInput && !emailChangeInput.disabled) {
      emailChangeInput.focus();
    }
  };

  if (emailChangeToggle && emailChangeForm) {
    emailChangeToggle.addEventListener("click", function () {
      setEmailChangeExpanded(true);
    });
  }

  if (emailChangeCancel && emailChangeForm) {
    emailChangeCancel.addEventListener("click", function () {
      emailChangeForm.reset();
      setEmailChangeExpanded(false);
    });
  }

  if (cooldownRemaining > 0) {
    const timer = document.getElementById("chg-t");
    const button = document.getElementById("chg-btn");
    const input = document.querySelector("#chg-form input[type=email]");
    const note = document.getElementById("chg-cd");
    const openButton = document.querySelector("[data-email-change-open]");
    let remaining = cooldownRemaining;

    const tickCooldown = function () {
      if (remaining <= 0) {
        if (button) {
          button.disabled = false;
        }
        if (input) {
          input.disabled = false;
        }
        if (openButton) {
          openButton.disabled = false;
        }
        if (note) {
          note.style.display = "none";
        }
        clearInterval(cooldownIntervalId);
        return;
      }

      if (timer) {
        timer.textContent = Math.floor(remaining / 60) + ":" + String(remaining % 60).padStart(2, "0");
      }
      remaining -= 1;
    };

    tickCooldown();
    var cooldownIntervalId = setInterval(tickCooldown, 1000);
  }

  document.querySelectorAll("[data-session-remaining]").forEach(function (stateBadge) {
    let remaining = Number(stateBadge.dataset.sessionRemaining || "0");
    const sessionSide = stateBadge.closest(".session-side");
    const state = sessionSide ? sessionSide.querySelector("[data-session-state]") : null;
    const logoutAction = sessionSide ? sessionSide.querySelector(".session-action") : null;
    const sessionCard = stateBadge.closest(".session-card");
    const tickSession = function () {
      if (remaining <= 0) {
        if (logoutAction) {
          logoutAction.remove();
        }
        if (state) {
          state.textContent = "Allowed";
          state.className = "session-state session-state-allowed";
          state.removeAttribute("data-session-remaining");
        }
        if (sessionCard) {
          sessionCard.classList.remove("active");
          sessionCard.classList.add("allowed");
        }
        clearInterval(sessionIntervalId);
        return;
      }
      if (state) {
        state.textContent = "Active";
        state.classList.toggle("session-state-active-warn", remaining <= 600);
      }
      remaining -= 1;
    };
    tickSession();
    var sessionIntervalId = setInterval(tickSession, 1000);
  });

  const settingsSessionRemaining = document.getElementById("settings-session-remaining");
  if (userSearchInput && userCards.length) {
    const filterUsers = function () {
      const query = userSearchInput.value.trim().toLowerCase();
      let visibleCount = 0;
      userCards.forEach(function (card) {
        const haystack = card.dataset.userSearch || "";
        const visible = !query || haystack.includes(query);
        card.style.display = visible ? "" : "none";
        if (visible) {
          visibleCount += 1;
        }
      });
      if (userSearchEmpty) {
        userSearchEmpty.classList.toggle("user-search-empty-hidden", visibleCount > 0);
      }
      syncCreateCardHeights();
    };
    userSearchInput.addEventListener("input", filterUsers);
    filterUsers();
  } else {
    syncCreateCardHeights();
  }

  window.addEventListener("resize", syncCreateCardHeights);

  if (!settingsSessionRemaining) {
    return;
  }

  let remaining = Number(settingsSessionRemaining.dataset.currentRemaining || "0");
  if (remaining <= 0) {
    settingsSessionRemaining.textContent = "Expired";
    return;
  }

  const tickNotice = function () {
    settingsSessionRemaining.textContent = remaining > 0
      ? Math.floor(remaining / 60) + ":" + String(remaining % 60).padStart(2, "0")
      : "Expired";
    if (remaining <= 0) {
      clearInterval(noticeIntervalId);
      setTimeout(function () {
        const logoutForm = document.querySelector('form[action="/smartlock/logout"]');
        if (logoutForm) {
          logoutForm.submit();
          return;
        }
        window.location.href = "/login";
      }, 5000);
      return;
    }

    remaining -= 1;
  };

  tickNotice();
  var noticeIntervalId = setInterval(tickNotice, 1000);
});
