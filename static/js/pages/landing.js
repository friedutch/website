document.addEventListener("DOMContentLoaded", function () {
  const shell = document.querySelector(".landing-shell");
  const logoLink = document.querySelector(".landing-logo-link");
  let isLeaving = false;

  if (!shell || !logoLink) {
    return;
  }

  function resetLandingState() {
    isLeaving = false;
    shell.classList.remove("is-leaving");
  }

  resetLandingState();

  logoLink.addEventListener("mouseenter", function () {
    const gradientAngle = Math.floor(Math.random() * 360);
    const rotation = Math.floor(Math.random() * 41) - 20;
    shell.style.setProperty("--landing-gradient-angle", gradientAngle + "deg");
    shell.style.setProperty("--landing-logo-rotation", rotation + "deg");
  });

  logoLink.addEventListener("click", function (event) {
    if (isLeaving) {
      event.preventDefault();
      return;
    }

    event.preventDefault();
    isLeaving = true;
    shell.classList.add("is-leaving");

    window.setTimeout(function () {
      window.location.href = logoLink.href;
    }, 240);
  });

  window.addEventListener("pageshow", resetLandingState);
});
