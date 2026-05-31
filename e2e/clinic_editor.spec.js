// Browser end-to-end test for the hybrid clinic-data editor (app/templates/tenant_edit.html).
//
// Drives the *real* client-side JS — guided forms, add/remove rows, weekday checkboxes,
// the hidden-field sync, and the actual form submit — then reloads and asserts the data
// persisted through the server's validate+normalize path into the DB.
//
// Why a browser test: the editor's correctness lives in JS that curl/pytest can't run
// (collect() → JSON → submit). Pure-Python tests cover normalize()/validate() and the
// save route; this covers the seam between the form and that route.
//
// Config via env (run.sh sets these): BASE, ADMIN_PASSWORD, TENANT_ID.
const { chromium } = require("playwright");

const BASE = process.env.BASE || "http://127.0.0.1:8099";
const PW = process.env.ADMIN_PASSWORD || "testpass123";
const TENANT = process.env.TENANT_ID || "2";
const SHOT = process.env.SCREENSHOT || "";

(async () => {
  // channel:"chrome" uses the system Google Chrome — no Playwright browser download needed.
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const page = await browser.newPage();
  const log = (...a) => console.log(...a);
  const editUrl = `${BASE}/admin/tenants/${TENANT}/edit`;

  // Pages keep an SSE stream open, so "networkidle" never settles — use "load".
  await page.goto(`${BASE}/admin/login`, { waitUntil: "domcontentloaded" });
  await page.fill('input[name="password"]', PW);
  await page.click('button[type="submit"], button');
  await page.waitForLoadState("load");

  await page.goto(editUrl, { waitUntil: "load" });
  const seeded = await page.inputValue('[data-c="name"]');
  log("STEP guided populated from server, clinic.name =", JSON.stringify(seeded));

  await page.fill('[data-c="name"]', "Driven Clinic");
  await page.fill('[data-c="phone"]', "+966-11-000-0000");
  await page.fill('[data-c="languages"]', "Arabic, English");

  await page.click('[data-add="services"]');
  const s = page.locator('#rows-services .row').last();
  await s.locator('[data-f="name"]').fill("Dental Cleaning");
  await s.locator('[data-f="price_sar"]').fill("400");
  await s.locator('[data-f="duration_min"]').fill("45");

  await page.click('[data-add="doctors"]');
  const d = page.locator('#rows-doctors .row').last();
  await d.locator('[data-f="name"]').fill("Dr. Test Driver");
  await d.locator('[data-f="specialty"]').fill("Dentist");
  await d.locator('[data-day][value="Monday"]').check();
  await d.locator('[data-day][value="Wednesday"]').check();
  await d.locator('[data-f="available_hours"]').fill("5:00 PM - 9:00 PM");

  await page.click('[data-add="faqs"]');
  const f = page.locator('#rows-faqs .row').last();
  await f.locator('[data-f="q"]').fill("Do you have parking?");
  await f.locator('[data-f="a"]').fill("Yes, free on-site.");

  await page.fill('[data-p="booking_lead_time_hours"]', "3");
  await page.check('[data-p="walk_ins_accepted"]');
  await page.locator('[data-p="booking_lead_time_hours"]').dispatchEvent("input");

  // The value that WOULD be submitted — client-side serialization.
  const obj = JSON.parse(await page.inputValue('#clinic_json'));
  log("STEP client serialized hidden field:",
      `clinic.name=${JSON.stringify(obj.clinic.name)}`,
      `| services=${obj.services.length}`,
      `| doctors=${obj.doctors.length}`,
      `| doctor.days=${JSON.stringify((obj.doctors[0] || {}).available_days)}`,
      `| faqs=${obj.faqs.length}`,
      `| lead=${obj.appointment_policy.booking_lead_time_hours}`,
      `| walkins=${obj.appointment_policy.walk_ins_accepted}`);

  await Promise.all([
    page.waitForNavigation({ waitUntil: "load" }).catch(() => {}),
    page.click('button:has-text("Save")'),
  ]);
  log("STEP submitted; landed on", page.url());

  // Reload and assert the server persisted what the browser sent.
  await page.goto(editUrl, { waitUntil: "load" });
  const saved = JSON.parse(await page.inputValue('#clinic_json'));
  const svc = saved.services.find((x) => x.name === "Dental Cleaning");
  const doc = saved.doctors.find((x) => x.name === "Dr. Test Driver");
  const faq = saved.faqs.find((x) => x.q === "Do you have parking?");
  log("VERIFY persisted after reload:",
      `clinic.name=${JSON.stringify(saved.clinic.name)}`,
      `| service price_sar=${svc && svc.price_sar} (${svc && typeof svc.price_sar})`,
      `| doctor.days=${JSON.stringify(doc && doc.available_days)}`,
      `| faq.a=${JSON.stringify(faq && faq.a)}`,
      `| lead=${saved.appointment_policy.booking_lead_time_hours}`);

  const ok =
    saved.clinic.name === "Driven Clinic" &&
    svc && svc.price_sar === 400 && typeof svc.price_sar === "number" &&
    doc && JSON.stringify(doc.available_days) === JSON.stringify(["Monday", "Wednesday"]) &&
    faq && faq.a === "Yes, free on-site." &&
    saved.appointment_policy.booking_lead_time_hours === 3 &&
    saved.appointment_policy.walk_ins_accepted === true;

  if (SHOT) await page.screenshot({ path: SHOT, fullPage: true });
  log(ok ? "RESULT: PASS — browser guided edit saved & persisted correctly"
         : "RESULT: FAIL — persisted data did not match");
  await browser.close();
  process.exit(ok ? 0 : 1);
})().catch((e) => { console.error("DRIVER ERROR:", e.message); process.exit(2); });
