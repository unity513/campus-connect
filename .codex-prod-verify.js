const { chromium } = require("playwright");

const edgePath = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const productionPrintingUrl = "https://app.lavida.agency/marketplace?route=print365";

async function snapshot(page) {
  return page.evaluate(() => {
    const viewport = document.documentElement.clientWidth;
    const form = document.getElementById("printOrderForm");
    const nav = document.querySelector(".bottom-nav");
    const action = document.getElementById("printNextButton");
    const offenders = [...document.body.querySelectorAll("*")]
      .filter((el) => {
        const rect = el.getBoundingClientRect();
        return rect.right > viewport + 1 || rect.left < -1;
      })
      .map((el) => {
        const rect = el.getBoundingClientRect();
        return {
          tag: el.tagName,
          id: el.id,
          className: String(el.className || ""),
          left: Math.round(rect.left),
          right: Math.round(rect.right),
          width: Math.round(rect.width),
        };
      })
      .slice(0, 8);

    return {
      url: location.href,
      dedicated: document.body.classList.contains("print-dedicated"),
      activeId: document.querySelector(".page-panel.active")?.id || "",
      kicker: document.getElementById("printStepKicker")?.textContent?.trim() || "",
      title: document.getElementById("printStepTitle")?.textContent?.trim() || "",
      formVisible: !!form && getComputedStyle(form).display !== "none",
      scrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      viewport,
      navGap: nav && action ? Math.round(nav.getBoundingClientRect().top - action.getBoundingClientRect().bottom) : null,
      offenders,
    };
  });
}

(async () => {
  const browser = await chromium.launch({ executablePath: edgePath, headless: true });
  const widths = [320, 360, 390, 430];
  const widthsResult = [];
  for (const width of widths) {
    const page = await browser.newPage({
      viewport: { width, height: 900 },
      deviceScaleFactor: 2,
      isMobile: true,
    });
    await page.goto(productionPrintingUrl, { waitUntil: "domcontentloaded", timeout: 45000 });
    await page.waitForTimeout(2000);
    widthsResult.push(await snapshot(page));
    await page.close();
  }

  const page = await browser.newPage({
    viewport: { width: 360, height: 900 },
    deviceScaleFactor: 2,
    isMobile: true,
  });
  await page.goto("https://app.lavida.agency/marketplace#home", {
    waitUntil: "domcontentloaded",
    timeout: 45000,
  });
  await page.waitForTimeout(2000);
  await page.click("[data-service-page='print365']");
  await page.waitForTimeout(2500);
  const afterClick = await snapshot(page);

  await page.goBack({ waitUntil: "domcontentloaded", timeout: 45000 }).catch(() => null);
  await page.waitForTimeout(1500);
  const afterBack = await snapshot(page);

  await page.goto(productionPrintingUrl, { waitUntil: "domcontentloaded", timeout: 45000 });
  await page.waitForTimeout(2000);
  const steps = [];
  for (let index = 0; index < 7; index += 1) {
    await page.evaluate((step) => eval(`showPrintStep(${step})`), index);
    await page.waitForTimeout(200);
    steps.push(await snapshot(page));
  }

  await browser.close();
  console.log(JSON.stringify({ widths: widthsResult, afterClick, afterBack, steps }, null, 2));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
