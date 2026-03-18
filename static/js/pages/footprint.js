document.addEventListener("DOMContentLoaded", function () {
  const state = { breaches: [], probes: [], addresses: [], bFilter: "all", pFilter: "all" };
  const statusLabel = { found: "Account found", not_found: "No account", inconclusive: "Inconclusive" };

  function switchTab(name, button) {
    document.querySelectorAll(".tab-panel").forEach(function (panel) { panel.classList.remove("active"); });
    document.querySelectorAll(".tab-btn").forEach(function (tab) { tab.classList.remove("active"); });
    const panel = document.getElementById("panel-" + name);
    if (panel) {
      panel.classList.add("active");
    }
    if (button) {
      button.classList.add("active");
    }
  }

  function updateMetrics() {
    document.getElementById("m-addresses").textContent = state.addresses.length;
    document.getElementById("m-breaches").textContent = state.breaches.length;
    document.getElementById("m-accounts").textContent = state.probes.filter(function (probe) { return probe.status === "found"; }).length;
    document.getElementById("tc-breaches").textContent = state.breaches.length;
    document.getElementById("tc-probe").textContent = state.probes.length;
    document.getElementById("tc-addresses").textContent = state.addresses.length;
  }

  function tagClass(tag) {
    const lowered = tag.toLowerCase();
    if (lowered.includes("password") || lowered.includes("credit")) return "tag-red";
    if (lowered.includes("phone") || lowered.includes("birth") || lowered.includes("name") || lowered.includes("locat")) return "tag-orange";
    return "tag-gray";
  }

  function renderBreaches() {
    let items = state.breaches;
    if (state.bFilter !== "all") {
      items = items.filter(function (breach) { return breach.severity === state.bFilter; });
    }
    const list = document.getElementById("breach-list");
    if (!items.length) {
      list.innerHTML = '<div class="no-items">No breaches match this filter 🎉</div>';
      return;
    }
    list.innerHTML = items.map(function (breach) {
      return '<div class="breach-card sev-' + breach.severity + '"><div class="breach-icon">' + breach.icon + '</div><div class="breach-body"><div class="breach-top"><span class="breach-site">' + breach.site + '</span><span class="breach-date">' + breach.date + '</span></div><div class="breach-email">' + breach.email + '</div><div class="tags">' + breach.tags.map(function (tag) { return '<span class="tag ' + tagClass(tag) + '">' + tag + '</span>'; }).join("") + "</div></div></div>";
    }).join("");
  }

  function renderProbe() {
    const search = (document.getElementById("probe-search").value || "").toLowerCase();
    let items = state.probes;
    if (state.pFilter !== "all") {
      items = items.filter(function (probe) { return probe.status === state.pFilter; });
    }
    if (search) {
      items = items.filter(function (probe) {
        return probe.site.toLowerCase().includes(search) || probe.email.toLowerCase().includes(search);
      });
    }
    const list = document.getElementById("probe-list");
    if (!items.length) {
      list.innerHTML = '<div class="no-items">No results match this filter</div>';
      return;
    }
    list.innerHTML = items.map(function (probe) {
      return '<div class="probe-card"><div class="probe-icon">' + probe.icon + '</div><div class="probe-info"><div class="probe-site">' + probe.site + '</div><div class="probe-email">' + probe.email + '</div></div><div class="probe-status ' + probe.status + '"><div class="status-dot dot-' + probe.status + '"></div>' + (statusLabel[probe.status] || probe.status) + "</div></div>";
    }).join("");
  }

  function renderAddresses() {
    const list = document.getElementById("addr-list");
    if (!state.addresses.length) {
      list.innerHTML = '<div class="no-items">No addresses found</div>';
      return;
    }
    list.innerHTML = state.addresses.map(function (address) {
      const status = address.breaches > 0
        ? '<span class="addr-stat addr-breach">⚠️ ' + address.breaches + " breach" + (address.breaches > 1 ? "es" : "") + "</span>"
        : '<span class="addr-stat addr-clean">✅ Clean</span>';
      return '<div class="addr-card"><span class="addr-icon">📧</span><span class="addr-email">' + address.email + "</span>" + status + "</div>";
    }).join("");
  }

  async function runScan() {
    const input = document.getElementById("scan-input");
    const value = input.value.trim();
    if (!value) {
      return;
    }

    const button = document.getElementById("scan-btn");
    button.textContent = "⏳ Scanning…";
    button.disabled = true;

    try {
      const response = await fetch("/footprint/scan", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": document.querySelector('input[name="csrf_token"]').value
        },
        body: JSON.stringify({ target: value })
      });
      const data = await response.json();
      state.breaches = data.breaches || [];
      state.probes = data.probes || [];
      state.addresses = data.addresses || [];
      document.getElementById("m-lastscan").textContent = data.scanned_at || "just now";
      updateMetrics();
      renderBreaches();
      renderProbe();
      renderAddresses();
    } catch (error) {
      console.error(error);
    } finally {
      button.textContent = "🚀 Scan";
      button.disabled = false;
    }
  }

  document.querySelectorAll("[data-tab-target]").forEach(function (button) {
    button.addEventListener("click", function () {
      switchTab(button.dataset.tabTarget, button);
    });
  });

  document.querySelectorAll("[data-breach-filter]").forEach(function (button) {
    button.addEventListener("click", function () {
      state.bFilter = button.dataset.breachFilter;
      document.querySelectorAll("#panel-breaches .filter-chip").forEach(function (chip) { chip.classList.remove("active"); });
      button.classList.add("active");
      renderBreaches();
    });
  });

  document.querySelectorAll("[data-probe-filter]").forEach(function (button) {
    button.addEventListener("click", function () {
      state.pFilter = button.dataset.probeFilter;
      document.querySelectorAll("#panel-probe .filter-chip").forEach(function (chip) { chip.classList.remove("active"); });
      button.classList.add("active");
      renderProbe();
    });
  });

  document.getElementById("scan-btn").addEventListener("click", runScan);
  document.getElementById("probe-search").addEventListener("input", renderProbe);
  document.getElementById("scan-input").addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
      runScan();
    }
  });
});
