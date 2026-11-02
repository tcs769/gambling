// Runs every browser module in order, one after the other, in a way that works on Windows, macOS and Linux (no shell syntax).
//   BASE_URL=http://localhost:3000 npm run e2e
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { join, dirname } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const modules = ["recording", "documents", "reading", "review", "goals", "invest", "compare", "navigation", "wording"];
let failed = false;
for (const name of modules) {
  console.log(`\n=== ${name} ===`);
  const result = spawnSync(process.execPath, [join(here, `${name}.mjs`)], { stdio: "inherit", env: process.env });
  if (result.status !== 0) {
    failed = true;
    console.log(`${name} failed`);
    break;
  }
}
process.exit(failed ? 1 : 0);
