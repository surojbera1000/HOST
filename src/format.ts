export const inr = (paise: number): string =>
  `₹${(paise / 100).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export function countdown(msLeft: number): string {
  const s = Math.max(0, Math.floor(msLeft / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function dateTime(ms: number): string {
  return new Date(ms).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" });
}

/** Escapes text for Telegram HTML parse mode. */
export function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

const FLAGS: Record<string, string> = {
  india: "🇮🇳",
  indonesia: "🇮🇩",
  "usa (virtual)": "🇺🇸",
  usa: "🇺🇸",
  "usa (2)": "🇺🇸",
  russia: "🇷🇺",
  china: "🇨🇳",
  philippines: "🇵🇭",
  vietnam: "🇻🇳",
  "united kingdom": "🇬🇧",
  england: "🇬🇧",
  chile: "🇨🇱",
  colombia: "🇨🇴",
  "south africa": "🇿🇦",
  brazil: "🇧🇷",
  nigeria: "🇳🇬",
  kenya: "🇰🇪",
  pakistan: "🇵🇰",
  bangladesh: "🇧🇩",
  "sri lanka": "🇱🇰",
  myanmar: "🇲🇲",
  thailand: "🇹🇭",
  malaysia: "🇲🇾",
  cambodia: "🇰🇭",
  poland: "🇵🇱",
  ukraine: "🇺🇦",
  kazakhstan: "🇰🇿",
  mexico: "🇲🇽",
  argentina: "🇦🇷",
  "hong kong": "🇭🇰",
  nepal: "🇳🇵",
  egypt: "🇪🇬",
  morocco: "🇲🇦",
};

/** A rough flag emoji by country name (decorative only). */
export function flag(name: string): string {
  return FLAGS[name.trim().toLowerCase()] ?? "🌐";
}
