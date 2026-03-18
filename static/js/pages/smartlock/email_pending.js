document.addEventListener("DOMContentLoaded", function () {
  const script = document.currentScript;
  const sentAt = new Date((script?.dataset.sentAt || "") + "Z");
  const interval = 5 * 60 * 1000;
  const button = document.getElementById("resend-btn");
  const timer = document.getElementById("timer");

  const tick = function () {
    const remaining = interval - (Date.now() - sentAt);
    if (remaining <= 0) {
      if (timer) {
        timer.textContent = "now";
      }
      if (button) {
        button.classList.remove("resend-btn-disabled");
        button.href = "/smartlock/change-email/resend";
      }
      clearInterval(intervalId);
      return;
    }

    if (timer) {
      const minutes = Math.floor(remaining / 60000);
      const seconds = String(Math.floor((remaining % 60000) / 1000)).padStart(2, "0");
      timer.textContent = minutes + ":" + seconds;
    }
  };

  tick();
  var intervalId = setInterval(tick, 1000);
});
