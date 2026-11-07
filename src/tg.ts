import { config } from "./config.js";

/**
 * Minimal Telegram Bot API client (raw fetch) so we can use the newest fields
 * like coloured button `style` (Bot API 9.4) and `copy_text` buttons (8.0+)
 * without waiting for a wrapper library to support them.
 */

export type ButtonStyle = "primary" | "success" | "danger";

export type InlineButton =
  | { text: string; callback_data: string; style?: ButtonStyle }
  | { text: string; url: string; style?: ButtonStyle }
  | { text: string; copy_text: { text: string }; style?: ButtonStyle };

export type InlineKeyboard = { inline_keyboard: InlineButton[][] };

export function kb(rows: InlineButton[][]): InlineKeyboard {
  return { inline_keyboard: rows.filter((r) => r.length > 0) };
}

/** A coloured callback button. */
export function btn(text: string, data: string, style?: ButtonStyle): InlineButton {
  return style ? { text, callback_data: data, style } : { text, callback_data: data };
}

export function urlBtn(text: string, url: string): InlineButton {
  return { text, url };
}

/** A button that copies text to the clipboard when tapped. */
export function copyBtn(text: string, value: string): InlineButton {
  return { text, copy_text: { text: value } };
}

export class TgApiError extends Error {
  constructor(
    public code: number,
    public description: string,
  ) {
    super(`Telegram ${code}: ${description}`);
  }
}

export async function call<T = unknown>(method: string, params: Record<string, unknown> = {}): Promise<T> {
  const res = await fetch(`https://api.telegram.org/bot${config.botToken}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
    signal: AbortSignal.timeout(method === "getUpdates" ? 70_000 : 30_000),
  });
  const data = (await res.json()) as { ok: boolean; result?: T; error_code?: number; description?: string };
  if (!data.ok) throw new TgApiError(data.error_code ?? res.status, data.description ?? "unknown");
  return data.result as T;
}

export type SentMessage = { message_id: number; chat: { id: number } };

export function sendMessage(
  chatId: number,
  text: string,
  keyboard?: InlineKeyboard,
): Promise<SentMessage> {
  return call<SentMessage>("sendMessage", {
    chat_id: chatId,
    text,
    parse_mode: "HTML",
    link_preview_options: { is_disabled: true },
    reply_markup: keyboard,
  });
}

export async function editMessage(
  chatId: number,
  messageId: number,
  text: string,
  keyboard?: InlineKeyboard,
): Promise<void> {
  try {
    await call("editMessageText", {
      chat_id: chatId,
      message_id: messageId,
      text,
      parse_mode: "HTML",
      link_preview_options: { is_disabled: true },
      reply_markup: keyboard,
    });
  } catch (err) {
    // "message is not modified" is harmless.
    if (err instanceof TgApiError && /not modified/i.test(err.description)) return;
    throw err;
  }
}

export async function sendPhoto(
  chatId: number,
  photo: Buffer,
  caption: string,
  keyboard?: InlineKeyboard,
): Promise<SentMessage> {
  const form = new FormData();
  form.set("chat_id", String(chatId));
  form.set("caption", caption);
  form.set("parse_mode", "HTML");
  if (keyboard) form.set("reply_markup", JSON.stringify(keyboard));
  form.set("photo", new Blob([new Uint8Array(photo)], { type: "image/png" }), "qr.png");
  const res = await fetch(`https://api.telegram.org/bot${config.botToken}/sendPhoto`, {
    method: "POST",
    body: form,
    signal: AbortSignal.timeout(30_000),
  });
  const data = (await res.json()) as { ok: boolean; result?: SentMessage; error_code?: number; description?: string };
  if (!data.ok) throw new TgApiError(data.error_code ?? res.status, data.description ?? "unknown");
  return data.result!;
}

export async function editCaption(
  chatId: number,
  messageId: number,
  caption: string,
  keyboard?: InlineKeyboard,
): Promise<void> {
  try {
    await call("editMessageCaption", {
      chat_id: chatId,
      message_id: messageId,
      caption,
      parse_mode: "HTML",
      reply_markup: keyboard,
    });
  } catch (err) {
    if (err instanceof TgApiError && /not modified/i.test(err.description)) return;
    throw err;
  }
}

export function answerCallback(id: string, text?: string, alert = false): Promise<unknown> {
  return call("answerCallbackQuery", { callback_query_id: id, text, show_alert: alert });
}

export function deleteMessage(chatId: number, messageId: number): Promise<unknown> {
  return call("deleteMessage", { chat_id: chatId, message_id: messageId }).catch(() => undefined);
}
