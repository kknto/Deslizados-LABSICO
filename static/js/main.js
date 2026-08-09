function loadScript(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.defer = true;
    script.onload = resolve;
    script.onerror = () => reject(new Error(`No se pudo cargar ${src}`));
    document.body.appendChild(script);
  });
}

function initLanding() {
  const landing = document.getElementById("landing-screen");
  const enterButton = document.getElementById("landing-enter");
  const mainContent = document.getElementById("main-content");
  if (!landing || !enterButton || !mainContent) return;

  enterButton.addEventListener("click", () => {
    landing.hidden = true;
    document.body.classList.remove("landing-active");
    mainContent.removeAttribute("inert");
    mainContent.focus({ preventScroll: true });
  });
}

initLanding();

loadScript("/js/app-state.js")
  .then(() => loadScript("/js/app-utils.js"))
  .then(() => loadScript("/js/app-charts.js"))
  .then(() => loadScript("/vendor/echarts.min.js"))
  .then(() => loadScript("/js/app-echarts.js"))
  .then(() => loadScript("/js/view-operational.js"))
  .then(() => loadScript("/js/view-operator.js"))
  .then(() => loadScript("/js/view-capture.js"))
  .then(() => loadScript("/js/view-program.js"))
  .then(() => loadScript("/js/view-report.js"))
  .then(() => loadScript("/js/legacy-app.js"));
