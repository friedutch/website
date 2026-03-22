document.addEventListener("DOMContentLoaded", function () {
  const script = document.getElementById("verification-complete-script");
  const redirectUrl = script?.dataset.redirectUrl || "/smartlock/admin";
  const loginSyncChannel = script?.dataset.loginSyncChannel || "";
  let notifiedAnotherPage = false;

  const payload = {
    type: "smartlock-login-complete",
    redirectUrl: redirectUrl,
    timestamp: Date.now()
  };

  if (loginSyncChannel && "BroadcastChannel" in window) {
    try {
      const channel = new BroadcastChannel(loginSyncChannel);
      channel.onmessage = function (event) {
        if (event?.data?.type === "smartlock-login-ack") {
          notifiedAnotherPage = true;
        }
      };
      channel.postMessage(payload);
      setTimeout(function () {
        channel.close();
      }, 1500);
    } catch (error) {
      // Ignore and fall back to storage events.
    }
  }

  if (loginSyncChannel && window.localStorage) {
    try {
      window.localStorage.setItem("smartlock-login-complete:" + loginSyncChannel, JSON.stringify(payload));
    } catch (error) {
      // Ignore storage failures and rely on direct fallback.
    }
  }

  setTimeout(function () {
    window.close();
  }, 200);

  setTimeout(function () {
    if (!notifiedAnotherPage) {
      window.location.replace(redirectUrl);
    }
  }, 1200);
});
