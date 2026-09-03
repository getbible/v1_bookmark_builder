#!/usr/bin/env node
// Dump the reviewed topic-name translations bundled in a getbible/robot
// checkout as one JSON document on stdout:
//   {
//     "locales": { "<locale>": { "<topic-id>": "<translated name>", ... }, ... },
//     "policy":  { "<locale>": "<source locale>", ... }
//   }
// `policy` lists the locales whose catalogue the robot fills from another
// locale (its BOOKMARK_LOCALE_POLICY_SOURCES); those are fallbacks inside the
// Mini App, not translations, and the importer skips them.
// Usage: node scripts/export_robot_locales.mjs /path/to/robot
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const robotRoot = process.argv[2];
if (!robotRoot) {
  process.stderr.write("Usage: export_robot_locales.mjs <robot checkout>\n");
  process.exit(2);
}
const modulePath = resolve(robotRoot, "miniapp/lib/bookmark-locales.js");
const { BOOKMARK_LOCALE_EXTENSION, BOOKMARK_LOCALE_POLICY_SOURCES } = await import(
  pathToFileURL(modulePath).href
);
const locales = {};
for (const locale of Object.keys(BOOKMARK_LOCALE_EXTENSION).sort()) {
  const catalog = BOOKMARK_LOCALE_EXTENSION[locale];
  const names = {};
  for (const key of Object.keys(catalog).sort()) {
    if (key.startsWith("bookmark_topics.")) {
      names[key.slice("bookmark_topics.".length)] = catalog[key];
    }
  }
  locales[locale] = names;
}
const policy = { ...(BOOKMARK_LOCALE_POLICY_SOURCES ?? {}) };
process.stdout.write(JSON.stringify({ locales, policy }, null, 2) + "\n");
