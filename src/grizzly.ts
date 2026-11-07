import { config } from "./config.js";

/** Client for the GrizzlySMS handler API (sms-activate compatible). The API key stays on the server. */

export class GrizzlyError extends Error {
  constructor(
    public code: string,
    message?: string,
  ) {
    super(message ?? code);
  }
}

async function call(params: Record<string, string | number | undefined>): Promise<string> {
  if (!config.grizzlyApiKey) throw new GrizzlyError("NO_KEY", "GRIZZLY_API_KEY is not set");
  const url = new URL(config.grizzlyBaseUrl);
  url.searchParams.set("api_key", config.grizzlyApiKey);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") url.searchParams.set(k, String(v));
  }
  const res = await fetch(url, {
    signal: AbortSignal.timeout(20_000),
    headers: { "User-Agent": "MikuOTPBot/1.0" },
  });
  const text = (await res.text()).trim();
  if (!res.ok) throw new GrizzlyError("HTTP_" + res.status, text.slice(0, 200));
  return text;
}

function parseJson<T>(text: string): T {
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new GrizzlyError(text.slice(0, 60) || "EMPTY_RESPONSE");
  }
}

const cache = new Map<string, { at: number; value: unknown }>();
async function cached<T>(key: string, ttlMs: number, fn: () => Promise<T>): Promise<T> {
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < ttlMs) return hit.value as T;
  const value = await fn();
  cache.set(key, { at: Date.now(), value });
  return value;
}

export async function getBalanceUsd(): Promise<number> {
  const text = await call({ action: "getBalance" });
  const m = /^ACCESS_BALANCE:([\d.]+)$/.exec(text);
  if (!m) throw new GrizzlyError(text);
  return Number(m[1]);
}

export type Service = { code: string; name: string };

export function getServices(): Promise<Service[]> {
  return cached("services", 60 * 60_000, async () => {
    const data = parseJson<{ services: Service[] }>(await call({ action: "getServicesList" }));
    return data.services ?? [];
  });
}

export function getCountries(): Promise<Map<string, string>> {
  return cached("countries", 60 * 60_000, async () => {
    const data = parseJson<Record<string, { id: number; eng: string }>>(await call({ action: "getCountries" }));
    const map = new Map<string, string>();
    for (const c of Object.values(data)) map.set(String(c.id), c.eng);
    return map;
  });
}

export type PriceEntry = { country: string; costUsd: number; count: number };

export async function getServicePrices(service: string, fresh = false): Promise<PriceEntry[]> {
  const load = async () => {
    const data = parseJson<Record<string, Record<string, { cost: number; count: number }>>>(
      await call({ action: "getPrices", service }),
    );
    const out: PriceEntry[] = [];
    for (const [country, services] of Object.entries(data)) {
      const p = services?.[service];
      if (p) out.push({ country, costUsd: Number(p.cost), count: Number(p.count) });
    }
    return out;
  };
  if (fresh) return load();
  return cached(`prices:${service}`, 60_000, load);
}

export async function getNumber(opts: {
  service: string;
  country: string;
  maxPrice: number;
}): Promise<{ activationId: string; phone: string }> {
  const text = await call({
    action: "getNumber",
    service: opts.service,
    country: opts.country,
    maxPrice: opts.maxPrice,
  });
  const m = /^ACCESS_NUMBER:(\d+):(\d+)$/.exec(text);
  if (!m) throw new GrizzlyError(text);
  return { activationId: m[1]!, phone: m[2]! };
}

export type ActivationStatus =
  | { state: "wait" }
  | { state: "code"; code: string }
  | { state: "cancelled" }
  | { state: "unknown"; raw: string };

export async function getStatus(activationId: string): Promise<ActivationStatus> {
  const text = await call({ action: "getStatus", id: activationId });
  if (text === "STATUS_WAIT_CODE" || text === "STATUS_WAIT_RESEND") return { state: "wait" };
  if (text.startsWith("STATUS_WAIT_RETRY")) return { state: "wait" };
  if (text.startsWith("STATUS_OK:")) return { state: "code", code: text.slice(10) };
  if (text === "STATUS_CANCEL") return { state: "cancelled" };
  return { state: "unknown", raw: text };
}

/** status: 1 = ready, 3 = request another SMS, 6 = finish, 8 = cancel */
export async function setStatus(activationId: string, status: 1 | 3 | 6 | 8): Promise<string> {
  return call({ action: "setStatus", id: activationId, status });
}

export function friendlyError(code: string): string {
  if (code.startsWith("NO_NUMBERS")) return "No numbers available right now. Try another country.";
  if (code.startsWith("NO_BALANCE")) return "This service is temporarily unavailable. Please try again later.";
  if (code.startsWith("EARLY_CANCEL_DENIED")) return "You can cancel only a few minutes after purchase. Please wait.";
  if (code.startsWith("BAD_SERVICE") || code.includes("prohibited")) return "This service is not available right now.";
  if (code.startsWith("WRONG_MAX_PRICE")) return "Price changed. Please go back and try again.";
  return "Provider error. Please try again.";
}
