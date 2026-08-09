/**
 * Dev entrypoint for `npm run dev`: spawn Next.js with forwarded CLI args.
 */

import { spawn } from "node:child_process";

const child = spawn("next", ["dev", ...process.argv.slice(2)], {
  env: process.env,
  stdio: "inherit",
  shell: true,
});

child.on("exit", (code) => {
  process.exit(code ?? 0);
});
