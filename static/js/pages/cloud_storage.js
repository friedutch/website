document.addEventListener("DOMContentLoaded", function () {
  const input = document.getElementById("cloud-file-input");
  const fileName = document.getElementById("cloud-file-name");

  if (!input || !fileName) {
    return;
  }

  input.addEventListener("change", function () {
    const selected = input.files && input.files[0];
    fileName.textContent = selected ? selected.name : "No file selected yet";
  });
});
