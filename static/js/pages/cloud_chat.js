document.addEventListener("DOMContentLoaded", function () {
  const searchInput = document.getElementById("cloudchat-user-search");
  const userCards = Array.from(document.querySelectorAll("[data-cloudchat-user-card]"));
  const emptyState = document.getElementById("cloudchat-user-search-empty");

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
