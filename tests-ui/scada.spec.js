const { test, expect } = require("@playwright/test");

test.describe("Lite simplificado", () => {
  test.beforeEach(async ({ page }) => {
    const consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (error) => consoleErrors.push(error.message));
    page.consoleErrors = consoleErrors;
    await page.goto("/", { waitUntil: "networkidle" });
  });

  test.afterEach(async ({ page }) => {
    expect(page.consoleErrors).toEqual([]);
  });

  test("muestra las pestanas Lite con bitacora separada", async ({ page }) => {
    const tabs = page.getByRole("tab");
    await expect(tabs).toHaveCount(5);
    await expect(page.getByRole("tab", { name: "Operador" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Captura" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Programa" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Bitacora" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Reporte" })).toBeVisible();

    for (const name of ["Inicio", "SCADA", "Zonas", "Tendencias", "Eventos", "Evidencia", "Sensores", "Diagnostico", "Calibracion"]) {
      await expect(page.getByRole("tab", { name })).toHaveCount(0);
    }
  });

  test("Bitacora permite OCR experimental, CSV manual y vista previa", async ({ page }) => {
    await page.getByRole("tab", { name: "Bitacora" }).click();
    for (const selector of [
      "#written-log-template-btn",
      "#written-log-auto-btn",
      "#written-log-ocr-status",
      "#written-log-base-date",
      "#written-log-mode",
      "#written-log-first-fresh-zone",
      "#written-log-create-advances",
      "#written-log-existing-advances-mode",
      "#written-log-events-mode",
      "#written-log-advance-interpretation",
      "#written-log-ollas-file",
      "#written-log-events-file",
      "#written-log-preview-btn",
      "#written-log-import-btn",
    ]) {
      await expect(page.locator(selector)).toBeVisible();
    }
  });

  test("Operador conserva decision, avance total, zonas y bitacora", async ({ page }) => {
    await page.getByRole("tab", { name: "Operador" }).click();
    for (const selector of [
      "#operator-status",
      "#operator-zone",
      "#operator-maturity",
      "#operator-total-advance",
      "#operator-zone-status-list",
      "#operator-temperature-trend",
      "#operator-data-check-list",
      "#data-quality-panel",
      "#operator-log-list",
      "#operator-action-btn",
    ]) {
      await expect(page.locator(selector)).toBeVisible();
    }
  });

  test("Captura mantiene colado, arranque con zona previa, ollas y lecturas", async ({ page }) => {
    await page.getByRole("tab", { name: "Captura" }).click();
    await expect(page.locator("#colado-form")).toBeVisible();
    await expect(page.locator("#start-offset-form")).toBeVisible();
    await expect(page.locator("#truck-zone-form")).toBeVisible();
    await expect(page.locator("#truck-loads-table")).toBeVisible();
    await expect(page.locator("#lectura-form")).toBeVisible();
    await expect(page.locator("#zone-reading-form")).toBeVisible();

    const startForm = page.locator("#start-offset-form");
    await startForm.locator("input[name='primera_zona_nueva']").fill("3");
    await expect(startForm.locator("input[name='zonas_previas_existentes']")).toHaveValue("2");
    await expect(page.locator("#start-offset-summary")).toContainText("Zona 1, Zona 2");
  });

  test("Captura permite editar receta y recalcula tolerancia", async ({ page }) => {
    await page.getByRole("tab", { name: "Captura" }).click();
    const form = page.locator("#advance-recipe-form");
    await form.locator("input[name='avance_objetivo_cm']").fill("5.0");
    await form.locator("input[name='intervalo_objetivo_min']").fill("5.0");
    await expect(form.locator("input[name='tolerancia_velocidad_min_cm_h']")).toHaveValue(/55(\.0)?/);
    await expect(form.locator("input[name='tolerancia_velocidad_max_cm_h']")).toHaveValue(/65(\.0)?/);
    await expect(page.locator("#advance-recipe-summary")).toContainText("60.0 cm/h");
  });

  test("Programa conserva escenarios 4h, 5h y 6h", async ({ page }) => {
    await page.getByRole("tab", { name: "Programa" }).click();
    for (const selector of [
      "#program-simple-zone",
      "#program-pass-4h-btn",
      "#program-fail-4h-btn",
      "#program-pass-5h-btn",
      "#program-fail-5h-btn",
      "#program-pass-6h-btn",
      "#program-fail-6h-btn",
      "#program-next-evaluation-btn",
      "#program-correct-result-btn",
      "#slip-schedule-form",
      "#program-layers-table",
    ]) {
      await expect(page.locator(selector)).toBeAttached();
    }
  });

  test("Reporte conserva exportaciones, semaforo y respaldo local", async ({ page }) => {
    await page.getByRole("tab", { name: "Reporte" }).click();
    for (const selector of [
      "#project-form",
      "#report-link",
      "#central-report-link",
      "#central-zip-link",
      "#report-photo-form",
      "#report-photos-list",
      "#export-link",
      "#bitacora-export-link",
      "#report-data-quality-panel",
      "#state-badge",
      "#readings-table",
      "#create-backup-btn",
      "#diagnostics-summary",
      "#backups-table",
    ]) {
      await expect(page.locator(selector)).toBeVisible();
    }
  });

  test("modal Operador captura temperatura y checklist rapido", async ({ page }) => {
    await page.evaluate(() => {
      window.__operatorDialogPromise = window.openOperatorDialog("slide");
    });
    await expect(page.locator("#operator-dialog")).toBeVisible();
    await page.locator("#operator-temp-input").fill("31.5");
    await page.locator("#operator-ambient-temp-input").fill("34.2");
    await page.locator("#operator-humidity-input").fill("78");
    await page.locator("#operator-dialog input[value='correcto']").check();
    for (const name of ["no_desmorona", "no_se_pega", "acabado_aceptable", "sin_arrastre"]) {
      await page.locator(`#operator-dialog input[name='${name}']`).check();
    }
    await page.locator("#operator-dialog-confirm").click();
    await expect(page.locator("#operator-dialog")).toBeHidden();
    const result = await page.evaluate(() => window.__operatorDialogPromise);
    expect(result.temperatura_concreto_c).toBe(31.5);
    expect(result.checklist.no_desmorona).toBe(true);
  });

  test("Operador abre captura rapida de temperatura por zona", async ({ page }) => {
    await page.evaluate(() => {
      const coladoId = window.SlipformApp.state.bootstrap?.colados?.[0]?.id || "1";
      window.SlipformApp.state.activeColadoId = String(coladoId);
      window.SlipformApp.state.moldState = {
        zona_en_liberacion: {
          id: 301,
          zona_numero: 3,
          elevacion_inferior_cm: 60,
          elevacion_superior_cm: 90,
          numero_olla: 3,
          hora_salida_planta: "2026-07-24T09:00",
        },
        zonas_activas: [
          {
            id: 301,
            zona_numero: 3,
            elevacion_inferior_cm: 60,
            elevacion_superior_cm: 90,
            numero_olla: 3,
            hora_salida_planta: "2026-07-24T09:00",
          },
        ],
      };
      window.__zoneTemperaturePromise = window.openOperatorZoneTemperatureDialog("301");
    });
    await expect(page.locator("#zone-temperature-dialog")).toBeVisible();
    await expect(page.locator("#zone-temperature-summary")).toContainText("Zona 3");
    await page.locator("#zone-temperature-input").fill("32.4");
    await page.locator("#zone-temperature-confirm").click();
    await expect(page.locator("#zone-temperature-dialog")).toBeHidden();
    const result = await page.evaluate(() => window.__zoneTemperaturePromise);
    expect(result.payload.zona_colado_id).toBe("301");
    expect(result.payload.colado_id).toBeTruthy();
    expect(result.payload.origen).toBe("manual");
    expect(Number(result.payload.temperatura_concreto_c)).toBe(32.4);
  });
});
