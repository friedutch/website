document.addEventListener("DOMContentLoaded", function () {
  const input = document.getElementById("cloud-file-input");
  const fileName = document.getElementById("cloud-file-name");
  const dropZone = document.getElementById("cloud-upload-drop");
  const uploadForm = document.getElementById("cloud-upload-form");
  const uploadQueue = document.getElementById("cloud-upload-queue");
  const uploadSubmit = document.getElementById("cloud-upload-submit");
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

  const humanSize = function (sizeBytes) {
    const units = ["B", "KB", "MB", "GB", "TB"];
    let size = Number(sizeBytes || 0);
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex += 1;
    }
    if (unitIndex === 0) {
      return Math.round(size) + " " + units[unitIndex];
    }
    return size.toFixed(1) + " " + units[unitIndex];
  };

  const syncFileLabel = function () {
    fileName.textContent = describeFiles(input.files);
  };

  const createUploadJob = function (file) {
    const card = document.createElement("div");
    card.className = "upload-job";
    card.innerHTML = [
      '<div class="upload-job-head">',
      '<div class="upload-job-name"></div>',
      '<div class="upload-job-state">Queued</div>',
      "</div>",
      '<div class="upload-job-progress"><div class="upload-job-fill"></div></div>',
      '<div class="upload-job-meta">',
      '<span class="upload-job-size"></span>',
      '<span class="upload-job-status">Waiting to start</span>',
      "</div>"
    ].join("");

    card.querySelector(".upload-job-name").textContent = file.name;
    card.querySelector(".upload-job-size").textContent = humanSize(file.size);
    uploadQueue.appendChild(card);
    uploadQueue.classList.remove("empty-hidden");
    return {
      card: card,
      state: card.querySelector(".upload-job-state"),
      status: card.querySelector(".upload-job-status"),
      fill: card.querySelector(".upload-job-fill")
    };
  };

  const updateJobProgress = function (job, sentBytes, totalBytes, stateText, statusText) {
    const percent = totalBytes > 0 ? Math.min(100, (sentBytes / totalBytes) * 100) : 0;
    job.fill.style.width = percent + "%";
    job.state.textContent = stateText;
    job.status.textContent = statusText;
  };

  const postForm = async function (url, formData) {
    const response = await fetch(url, {
      method: "POST",
      body: formData,
      credentials: "same-origin"
    });
    let data = {};
    try {
      data = await response.json();
    } catch (error) {
      data = {};
    }
    if (!response.ok) {
      throw new Error(data.error || "Upload request failed.");
    }
    return data;
  };

  const uploadFileInChunks = async function (file, csrfToken, job) {
    const startData = new FormData();
    startData.append("csrf_token", csrfToken);
    startData.append("name", file.name);
    startData.append("size", String(file.size));
    startData.append("mime_type", file.type || "");
    const started = await postForm("/cloud-storage/upload/start", startData);
    const uploadId = started.upload_id;
    const chunkSize = Number(started.chunk_size || 0) || (8 * 1024 * 1024);

    let offset = 0;
    try {
      while (offset < file.size) {
        const nextChunk = file.slice(offset, offset + chunkSize);
        const chunkData = new FormData();
        chunkData.append("csrf_token", csrfToken);
        chunkData.append("offset", String(offset));
        chunkData.append("chunk", nextChunk, file.name);
        updateJobProgress(job, offset, file.size, "Uploading", "Sending " + humanSize(offset) + " of " + humanSize(file.size));
        const chunkResponse = await postForm("/cloud-storage/upload/chunk/" + uploadId, chunkData);
        offset = Number(chunkResponse.received_size || 0);
      }

      updateJobProgress(job, file.size, file.size, "Finalizing", "Saving metadata and checksum");
      const finishData = new FormData();
      finishData.append("csrf_token", csrfToken);
      await postForm("/cloud-storage/upload/finish/" + uploadId, finishData);
      job.card.classList.add("upload-job-complete");
      updateJobProgress(job, file.size, file.size, "Complete", "Uploaded successfully");
    } catch (error) {
      job.card.classList.add("upload-job-error");
      job.state.textContent = "Failed";
      job.status.textContent = error.message;
      job.fill.style.width = "100%";
      try {
        const cancelData = new FormData();
        cancelData.append("csrf_token", csrfToken);
        await fetch("/cloud-storage/upload/cancel/" + uploadId, {
          method: "POST",
          body: cancelData,
          credentials: "same-origin"
        });
      } catch (cancelError) {
        // Ignore cleanup failures in the browser.
      }
      throw error;
    }
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

  if (uploadForm && uploadQueue && uploadSubmit) {
    uploadForm.addEventListener("submit", async function (event) {
      event.preventDefault();

      if (!input.files || !input.files.length) {
        return;
      }

      const csrfInput = uploadForm.querySelector('input[name="csrf_token"]');
      const csrfToken = csrfInput ? csrfInput.value : "";
      const selectedFiles = Array.from(input.files);
      const jobs = selectedFiles.map(createUploadJob);
      let hadError = false;

      uploadSubmit.disabled = true;
      input.disabled = true;
      dropZone.classList.add("upload-drop-active");

      for (let index = 0; index < selectedFiles.length; index += 1) {
        try {
          await uploadFileInChunks(selectedFiles[index], csrfToken, jobs[index]);
        } catch (error) {
          hadError = true;
        }
      }

      uploadSubmit.disabled = false;
      input.disabled = false;
      dropZone.classList.remove("upload-drop-active");
      input.value = "";
      syncFileLabel();

      if (!hadError) {
        window.setTimeout(function () {
          window.location.reload();
        }, 900);
      }
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
