document.addEventListener("DOMContentLoaded", function () {
  const searchInput = document.getElementById("cloudchat-user-search");
  const userCards = Array.from(document.querySelectorAll("[data-cloudchat-user-card]"));
  const emptyState = document.getElementById("cloudchat-user-search-empty");
  const passwordPreviewInput = document.querySelector("[data-password-preview-input]");
  const passwordPreviewToggle = document.querySelector("[data-password-preview-toggle]");
  const passwordPreviewCopy = document.querySelector("[data-password-preview-copy]");

  if (passwordPreviewInput && passwordPreviewToggle) {
    passwordPreviewToggle.addEventListener("click", function () {
      const revealing = passwordPreviewInput.type === "text";
      passwordPreviewInput.type = revealing ? "password" : "text";
      passwordPreviewToggle.textContent = revealing ? "Reveal" : "Hide";
    });
  }

  if (passwordPreviewInput && passwordPreviewCopy) {
    passwordPreviewCopy.addEventListener("click", async function () {
      try {
        await window.navigator.clipboard.writeText(passwordPreviewInput.value);
        passwordPreviewCopy.textContent = "Copied";
        window.setTimeout(function () {
          passwordPreviewCopy.textContent = "Copy";
        }, 1400);
      } catch (error) {
        passwordPreviewCopy.textContent = "Copy failed";
        window.setTimeout(function () {
          passwordPreviewCopy.textContent = "Copy";
        }, 1400);
      }
    });
  }

  if (!searchInput || !userCards.length) {
    return;
  }

  const filterUsers = function () {
    const query = searchInput.value.trim().toLowerCase();
    let visibleCount = 0;

    userCards.forEach(function (card) {
      const haystack = card.dataset.cloudchatUserSearch || "";
      const visible = !query || haystack.includes(query);
      card.style.display = visible ? "" : "none";
      if (visible) {
        visibleCount += 1;
      }
    });

    if (emptyState) {
      emptyState.classList.toggle("empty-hidden", visibleCount > 0);
    }
  };

  searchInput.addEventListener("input", filterUsers);
  filterUsers();
});
