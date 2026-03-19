document.addEventListener("DOMContentLoaded", function () {
  const script = document.getElementById("admin-panel-script");
  const cooldownRemaining = Number(script?.dataset.cooldownRemaining || "0");
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
    const nextTab = tabExists ? name : "settings";
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
    let initialTab = storage.get(tabStorageKey) || "settings";
    activateTab(initialTab);
  }

  const userSearchInput = document.getElementById("user-search");
  const userCards = Array.from(document.querySelectorAll("[data-user-card]"));
  const userSearchEmpty = document.getElementById("user-search-empty");
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
    };
    userSearchInput.addEventListener("input", filterUsers);
    filterUsers();
  }

  if (cooldownRemaining > 0) {
    const timer = document.getElementById("chg-t");
    const button = document.getElementById("chg-btn");
    const input = document.querySelector("#chg-form input[type=email]");
    const note = document.getElementById("chg-cd");
    let remaining = cooldownRemaining;

    const tickCooldown = function () {
      if (remaining <= 0) {
        if (button) {
          button.disabled = false;
        }
        if (input) {
          input.disabled = false;
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
    let elapsed = Number(stateBadge.dataset.sessionElapsed || "0");
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
        state.textContent = "Active (" + Math.floor(elapsed / 60) + ":" + String(elapsed % 60).padStart(2, "0") + ")";
        state.classList.toggle("session-state-active-warn", remaining <= 600);
      }
      elapsed += 1;
      remaining -= 1;
    };
    tickSession();
    var sessionIntervalId = setInterval(tickSession, 1000);
  });

  const sessionNotice = document.getElementById("sess-notif-top");
  if (!sessionNotice) {
    return;
  }

  let remaining = Number(sessionNotice.dataset.currentRemaining || "0");
  if (remaining <= 0) {
    return;
  }

  const timer = document.getElementById("notif-timer-top");
  const icon = document.getElementById("notif-icon-top");
  let warned = false;
  sessionNotice.classList.remove("sess-chip-hidden");

  const tickNotice = function () {
    if (remaining <= 0) {
      if (timer) {
        timer.textContent = "Expired";
      }
      sessionNotice.className = "sess-chip warn";
      if (icon) {
        icon.textContent = "🔴";
      }
      clearInterval(noticeIntervalId);
      setTimeout(function () {
        window.location.href = "/smartlock/logout";
      }, 5000);
      return;
    }

    if (timer) {
      timer.textContent = Math.floor(remaining / 60) + ":" + String(remaining % 60).padStart(2, "0");
    }
    if (remaining <= 300) {
      sessionNotice.className = "sess-chip warn";
      if (icon) {
        icon.textContent = "⚠️";
      }
      if (!warned) {
        warned = true;
        sessionNotice.style.transform = "scale(1.05)";
        setTimeout(function () {
          sessionNotice.style.transform = "scale(1)";
        }, 400);
      }
    } else {
      sessionNotice.className = "sess-chip ok";
      if (icon) {
        icon.textContent = "🟢";
      }
    }

    remaining -= 1;
  };

  tickNotice();
  var noticeIntervalId = setInterval(tickNotice, 1000);
});
