import { db, getSettingNumber } from "./db.js";

export type PriceRule = {
  id: number;
  service: string;
  country: string; // '*' = all countries
  mode: "default" | "markup" | "fixed" | "plus";
  value: number;
  hidden: number;
};

export function getPriceRules(): PriceRule[] {
  return db().prepare("SELECT * FROM price_rules ORDER BY service, country").all() as PriceRule[];
}

export type Pricer = (service: string, country: string, costUsd: number) => { pricePaise: number; hidden: boolean };

/**
 * Builds the current pricing function.
 * Rule priority: service+country > service+'*' > '*'+country > global markup.
 * Modes:
 *   default : cost × rate
 *   markup  : cost × rate × (1 + value%/100)
 *   plus    : cost × rate + value ₹   (this is the ₹40 WhatsApp margin)
 *   fixed   : value ₹ (flat total)
 */
export function makePricer(): Pricer {
  const rate = getSettingNumber("usd_inr_rate");
  const globalMarkup = getSettingNumber("global_markup_pct");
  const rules = new Map<string, PriceRule>();
  for (const r of getPriceRules()) rules.set(`${r.service}|${r.country}`, r);

  return (service, country, costUsd) => {
    const rule = rules.get(`${service}|${country}`) ?? rules.get(`${service}|*`) ?? rules.get(`*|${country}`);
    const hidden = Boolean(rule?.hidden);
    const base = costUsd * rate;
    let rupees: number;
    if (rule?.mode === "fixed" && rule.value > 0) rupees = rule.value;
    else if (rule?.mode === "plus") rupees = base + rule.value;
    else if (rule?.mode === "markup") rupees = base * (1 + rule.value / 100);
    else rupees = base * (1 + globalMarkup / 100);
    return { pricePaise: Math.max(1, Math.ceil(rupees * 100)), hidden };
  };
}

export function costPaise(costUsd: number): number {
  return Math.round(costUsd * getSettingNumber("usd_inr_rate") * 100);
}
