document.addEventListener("DOMContentLoaded", function () {
  const script = document.getElementById("admin-login-script");
  const linkCooldown = Number(script?.dataset.linkCooldown || "0");
  const shouldPollLogin = script?.dataset.pollLogin === "true";

  if (linkCooldown > 0) {
    const timer = document.getElementById("lk-timer");
    let remaining = linkCooldown;
    const tick = function () {
      if (remaining <= 0) {
        window.location.reload();
        clearInterval(intervalId);
        return;
      }
      if (timer) {
        timer.textContent = Math.floor(remaining / 60) + ":" + String(remaining % 60).padStart(2, "0");
      }
      remaining -= 1;
    };
    tick();
    var intervalId = setInterval(tick, 1000);
  }

  if (shouldPollLogin) {
    const poll = function () {
      fetch("/smartlock/poll-status")
        .then(function (response) { return response.json(); })
        .then(function (data) {
          if (data.status === "logged_in") {
            window.close();
            document.body.innerHTML = '<div class="login-success-message">✅ Logged in! You can close this tab.</div>';
            return;
          }
          setTimeout(poll, 2000);
        })
        .catch(function () {
          setTimeout(poll, 3000);
        });
    };
    setTimeout(poll, 2000);
  }
});
