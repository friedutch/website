document.addEventListener("DOMContentLoaded", function () {
  const timer = document.getElementById("exp-timer");
  if (timer) {
    let remaining = Number(timer.dataset.remaining || "0");
    const tick = function () {
      if (remaining <= 0) {
        timer.textContent = "expired";
        clearInterval(intervalId);
        return;
      }
      timer.textContent = Math.floor(remaining / 60) + ":" + String(remaining % 60).padStart(2, "0");
      remaining -= 1;
    };
    tick();
    var intervalId = setInterval(tick, 1000);
  }

  const copyButton = document.querySelector(".copy-join-url-btn");
  if (copyButton) {
    copyButton.addEventListener("click", async function () {
      await navigator.clipboard.writeText(copyButton.dataset.copyText || "");
      copyButton.textContent = "✅ Copied!";
    });
  }
});
