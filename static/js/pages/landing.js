document.addEventListener("DOMContentLoaded", function () {
  const shell = document.querySelector(".landing-shell");
  const logoLink = document.querySelector(".landing-logo-link");

  if (!shell || !logoLink) {
    return;
  }

  logoLink.addEventListener("mouseenter", function () {
    const gradientAngle = Math.floor(Math.random() * 360);
    const rotation = Math.floor(Math.random() * 41) - 20;
    shell.style.setProperty("--landing-gradient-angle", gradientAngle + "deg");
    shell.style.setProperty("--landing-logo-rotation", rotation + "deg");
  });
});
