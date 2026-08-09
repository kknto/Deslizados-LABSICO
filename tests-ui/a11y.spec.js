const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;

async function scan(page) {
  return new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .exclude(".echart canvas")
    .analyze();
}

test("Landing LABSICO no tiene violaciones WCAG A/AA criticas", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });
  const results = await scan(page);
  expect(results.violations).toEqual([]);
});

for (const tabName of ["Operador", "Captura", "Programa", "Bitacora", "Reporte"]) {
  test(`${tabName} no tiene violaciones WCAG A/AA criticas`, async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "Entrar al sistema" }).click();
    await page.getByRole("tab", { name: tabName }).click();
    const results = await scan(page);
    expect(results.violations).toEqual([]);
  });
}
