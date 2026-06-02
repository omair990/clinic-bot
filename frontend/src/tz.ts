/**
 * Display timezone + name/date formatting helpers used across the console.
 *
 * The active timezone is the clinic's own zone (the super-admin sees the platform default),
 * delivered by /me and set once at login via setDisplayTz. All time rendering goes through
 * here so every page shows clinic-local times rather than the viewer's browser timezone.
 */
let _tz: string | undefined;

export function setDisplayTz(tz?: string | null) { _tz = tz || undefined; }
export function getDisplayTz() { return _tz; }

const withTz = (o: Intl.DateTimeFormatOptions = {}) => (_tz ? { ...o, timeZone: _tz } : o);

// Locale for date formatting, derived from the live document language set by i18n. For Arabic
// we use "ar-u-nu-latn" so month/weekday names localize while digits stay Latin (consistent
// with times elsewhere). undefined = the browser default for English.
function isAr(): boolean { return typeof document !== "undefined" && document.documentElement.lang === "ar"; }
function locale(): string | undefined { return isAr() ? "ar-u-nu-latn" : undefined; }
const REL = {
  en: { today: "Today", tomorrow: "Tomorrow", yesterday: "Yesterday", undated: "Undated", unknown: "Unknown patient" },
  ar: { today: "اليوم", tomorrow: "غدًا", yesterday: "أمس", undated: "بدون تاريخ", unknown: "مريض غير معروف" },
};
const rel = () => (isAr() ? REL.ar : REL.en);

/** "01 Jun, 14:30" in the clinic timezone. */
export function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso);
  return d.toLocaleString(locale(), withTz({ day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }));
}

/** "14:30" in the clinic timezone. */
export function fmtTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString(locale(), withTz({ hour: "2-digit", minute: "2-digit" }));
}

// "YYYY-MM-DD" for the date as seen in the clinic timezone (en-CA gives ISO order).
function ymd(d: Date): string { return d.toLocaleDateString("en-CA", withTz()); }

/** Today / Tomorrow / Yesterday / weekday-date, relative to the clinic timezone. */
export function dayLabel(iso?: string | null): string {
  const r = rel();
  if (!iso) return r.undated;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return r.undated;
  const a = ymd(d), b = ymd(new Date());
  if (a === b) return r.today;
  const diff = Math.round((Date.parse(a) - Date.parse(b)) / 86400000);
  if (diff === 1) return r.tomorrow;
  if (diff === -1) return r.yesterday;
  const sameYear = a.slice(0, 4) === b.slice(0, 4);
  return d.toLocaleDateString(locale(), withTz({ weekday: "long", day: "2-digit", month: "short", ...(sameYear ? {} : { year: "numeric" }) }));
}

/** A friendly patient label: their name, else their number, else a clear placeholder. */
export function displayName(name?: string | null, wa?: string | null): string {
  const n = (name || "").trim();
  if (n) return n;
  return wa ? `+${wa}` : rel().unknown;
}

/** Two-letter avatar initials from a name, falling back to the last digits of the number. */
export function initials(name?: string | null, wa?: string | null): string {
  const n = (name || "").trim();
  if (n) {
    const parts = n.split(/\s+/);
    return ((parts[0]?.[0] || "") + (parts[1]?.[0] || parts[0]?.[1] || "")).toUpperCase() || "?";
  }
  return (wa || "").slice(-2) || "?";
}
