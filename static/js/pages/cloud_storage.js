document.addEventListener("DOMContentLoaded", function () {
  const input = document.getElementById("cloud-file-input");
  const fileName = document.getElementById("cloud-file-name");
  const dropZone = document.getElementById("cloud-upload-drop");
  const searchInput = document.getElementById("cloud-file-search");
  const fileCards = Array.from(document.querySelectorAll("[data-file-card]"));
  const emptyState = document.getElementById("cloud-file-search-empty");

  if (!input || !fileName) {
    return;
  }

  const describeFiles = function (files) {
    if (!files || !files.length) {
      return "No files selected yet";
    }
    if (files.length === 1) {
      return files[0].name;
    }
    return files.length + " files selected";
  };

  const syncFileLabel = function () {
    fileName.textContent = describeFiles(input.files);
  };

  input.addEventListener("change", syncFileLabel);
  syncFileLabel();

  if (dropZone) {
    ["dragenter", "dragover"].forEach(function (eventName) {
      dropZone.addEventListener(eventName, function (event) {
        event.preventDefault();
        dropZone.classList.add("upload-drop-active");
      });
    });

    ["dragleave", "dragend", "drop"].forEach(function (eventName) {
      dropZone.addEventListener(eventName, function (event) {
        event.preventDefault();
        if (eventName === "drop" && event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files.length) {
          input.files = event.dataTransfer.files;
          syncFileLabel();
        }
        dropZone.classList.remove("upload-drop-active");
      });
    });
  }

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
