import { startAdminPanel } from "./admin.js";
import { handleUpdate } from "./bot.js";
import { assertConfig } from "./config.js";
import { db, getState, setState } from "./db.js";
import { call } from "./tg.js";
import { startWorkers } from "./workers.js";

type Update = Parameters<typeof handleUpdate>[0];

async function setCommands(): Promise<void> {
  await call("setMyCommands", {
    commands: [
      { command: "start", description: "Open the menu" },
      { command: "balance", description: "Show your balance" },
    ],
  }).catch((e) => console.error("[bot] setMyCommands", e instanceof Error ? e.message : e));
}

/** Long-polling loop. Works on a VPS without any public webhook URL. */
async function pollLoop(): Promise<void> {
  // Drop any webhook so getUpdates is allowed.
  await call("deleteWebhook", { drop_pending_updates: false }).catch(() => undefined);
  let offset = Number(getState("tg_offset") ?? 0);
  console.log("[bot] long-polling started");
  for (;;) {
    try {
      const updates = await call<Update[]>("getUpdates", {
        offset,
        timeout: 50,
        allowed_updates: ["message", "callback_query"],
      });
      for (const u of updates) {
        offset = u.update_id + 1;
        await handleUpdate(u);
      }
      if (updates.length) setState("tg_offset", String(offset));
    } catch (err) {
      console.error("[bot] poll error", err instanceof Error ? err.message : err);
      await new Promise((r) => setTimeout(r, 3000));
    }
  }
}

async function main(): Promise<void> {
  assertConfig();
  db(); // open + migrate + seed
  startAdminPanel();
  startWorkers();
  await setCommands();
  await pollLoop();
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});
