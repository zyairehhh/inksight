import { spawn } from "node:child_process";
import { resolve } from "node:path";

const mode = process.argv[2];
const allowedModes = new Set(["dev", "start"]);

if (!allowedModes.has(mode)) {
  console.error("Usage: node scripts/run-next.mjs <dev|start>");
  process.exit(1);
}

const port = (process.env.ADMIN_CONSOLE_PORT || process.env.PORT || "").trim();
if (!port) {
  console.error("Missing ADMIN_CONSOLE_PORT (or PORT). Refusing to start adminapp with a hard-coded port.");
  process.exit(1);
}

const host = (process.env.ADMIN_CONSOLE_HOST || "").trim();
const nextBin = resolve(process.cwd(), "node_modules", ".bin", "next");
const args = [mode, "-p", port];

if (host) {
  args.push("-H", host);
}

const child = spawn(nextBin, args, {
  stdio: "inherit",
  env: process.env,
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});
