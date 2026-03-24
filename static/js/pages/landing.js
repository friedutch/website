document.addEventListener("DOMContentLoaded", function () {
  const shell = document.querySelector(".landing-shell");
  const logoLink = document.querySelector(".landing-logo-link");

  if (!shell || !logoLink) {
    return;
  }

  logoLink.addEventListener("mouseenter", function () {
    const angle = Math.floor(Math.random() * 360);
    shell.style.setProperty("--landing-gradient-angle", angle + "deg");
  });
});
