import { getCountries, getServicePrices, getServices } from "./grizzly.js";
import { makePricer } from "./pricing.js";

/** Service codes shown first in the bot, in this order. */
export const POPULAR = ["wa", "tg", "go", "ig", "fb", "lf", "fu", "am", "tw", "ds", "nf", "ub", "bye", "mb", "ot"];

export type ServiceOption = { code: string; name: string };

export async function popularServices(): Promise<ServiceOption[]> {
  const all = await getServices();
  const byCode = new Map(all.map((s) => [s.code, s]));
  const out: ServiceOption[] = [];
  for (const code of POPULAR) {
    const s = byCode.get(code);
    if (s) out.push({ code: s.code, name: s.name });
  }
  return out;
}

export async function searchServices(query: string): Promise<ServiceOption[]> {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const all = await getServices();
  return all
    .filter((s) => s.name.toLowerCase().includes(q) || s.code === q)
    .sort((a, b) => Number(!a.name.toLowerCase().startsWith(q)) - Number(!b.name.toLowerCase().startsWith(q)))
    .slice(0, 24)
    .map((s) => ({ code: s.code, name: s.name }));
}

export function serviceName(all: ServiceOption[], code: string): string {
  return all.find((s) => s.code === code)?.name ?? code;
}

export type CountryOption = { country: string; name: string; count: number; pricePaise: number };

/** Countries for a service with the final (marked-up) price, cheapest first, visible only. */
export async function countryOptions(service: string): Promise<CountryOption[]> {
  const [prices, countries] = await Promise.all([getServicePrices(service), getCountries()]);
  const price = makePricer();
  return prices
    .filter((p) => p.count > 0 && countries.has(p.country))
    .map((p) => {
      const { pricePaise, hidden } = price(service, p.country, p.costUsd);
      return { country: p.country, name: countries.get(p.country)!, count: p.count, pricePaise, hidden };
    })
    .filter((p) => !p.hidden)
    .map(({ country, name, count, pricePaise }) => ({ country, name, count, pricePaise }))
    .sort((a, b) => a.pricePaise - b.pricePaise);
}
