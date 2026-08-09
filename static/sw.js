const CACHE_NAME = "seybaplaya-slipform-lite-v19";
const ASSETS = [
  "/",
  "/index.html",
  "/assets/labsico-logo.jpg",
  "/css/main.css",
  "/css/base.css",
  "/css/scada.css",
  "/css/captura.css",
  "/css/lite-ux.css",
  "/css/legacy.css",
  "/styles.css",
  "/js/main.js",
  "/js/app-state.js",
  "/js/app-utils.js",
  "/js/app-charts.js",
  "/js/app-echarts.js",
  "/vendor/echarts.min.js",
  "/js/view-operational.js",
  "/js/view-operator.js",
  "/js/view-capture.js",
  "/js/view-program.js",
  "/js/view-report.js",
  "/js/legacy-app.js",
  "/app.js",
  "/manifest.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});
