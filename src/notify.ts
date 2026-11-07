import { config } from "./config.js";
import { sendMessage } from "./tg.js";

/** Sends a message to every admin Telegram ID. Best-effort. */
export async function notifyAdmins(text: string): Promise<void> {
  await Promise.all(
    config.adminTelegramIds.map((id) =>
      sendMessage(id, text).catch((e) => console.error("[notify] admin", id, e instanceof Error ? e.message : e)),
    ),
  );
}
