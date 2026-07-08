// TODO: Remove --test mock data mode before final project delivery

import { spawn } from "node:child_process";

const args = process.argv.slice(2);
const testMode = args.includes("--test");
const nextArgs = args.filter((arg) => arg !== "--test");

const env = { ...process.env };
if (testMode) {
  env.NEXT_PUBLIC_USE_MOCK_DATA = "true";
}

const child = spawn("next", ["dev", ...nextArgs], {
  env,
  stdio: "inherit",
  shell: true,
});

child.on("exit", (code) => {
  process.exit(code ?? 0);
});
