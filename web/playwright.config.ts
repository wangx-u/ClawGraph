import { defineConfig } from "@playwright/test";

const port = Number(process.env.PORT ?? 3410);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: {
    timeout: 15_000
  },
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    channel: "chrome",
    trace: "retain-on-failure"
  },
  webServer: {
    command: "bash ./scripts/run_e2e_server.sh",
    url: `http://127.0.0.1:${port}`,
    timeout: 180_000,
    reuseExistingServer: false,
    env: {
      ...process.env,
      PORT: String(port)
    }
  }
});
