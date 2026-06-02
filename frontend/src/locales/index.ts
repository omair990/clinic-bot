/**
 * Merges every namespace file under ./ns into a single { en, ar } dictionary.
 *
 * Each ./ns/<name>.ts exports `{ en: {...}, ar: {...} }`; its filename becomes the
 * namespace, so `t("<name>.<key>")` resolves here. Using import.meta.glob means adding a
 * new translated page is just dropping a file in ./ns — no edits to this index.
 */
const mods = import.meta.glob("./ns/*.ts", { eager: true }) as Record<
  string, { default: { en: Record<string, any>; ar: Record<string, any> } }
>;

const en: Record<string, any> = {};
const ar: Record<string, any> = {};
for (const path in mods) {
  const ns = path.split("/").pop()!.replace(/\.ts$/, "");
  en[ns] = mods[path].default.en;
  ar[ns] = mods[path].default.ar;
}

export const dict = { en, ar };
