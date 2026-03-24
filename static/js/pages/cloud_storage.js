document.addEventListener("DOMContentLoaded", function () {
  const input = document.getElementById("cloud-file-input");
  const fileName = document.getElementById("cloud-file-name");
  const searchInput = document.getElementById("cloud-file-search");
  const fileCards = Array.from(document.querySelectorAll("[data-file-card]"));
  const emptyState = document.getElementById("cloud-file-search-empty");

  if (!input || !fileName) {
    return;
  }

  input.addEventListener("change", function () {
    const selected = input.files && input.files[0];
    fileName.textContent = selected ? selected.name : "No file selected yet";
  });

  if (searchInput && fileCards.length) {
    const filterFiles = function () {
      const query = searchInput.value.trim().toLowerCase();
      let visibleCount = 0;
      fileCards.forEach(function (card) {
        const haystack = card.dataset.fileSearch || "";
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
    searchInput.addEventListener("input", filterFiles);
    filterFiles();
  }
});
