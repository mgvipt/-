/* Довідник одиниць виміру — ОДИН на всю CRM (01.10.2026, Олег).
 * Список живе в Складі → «Одиниці виміру»; тут лише кеш, щоб кожна форма
 * не тягнула його заново. Після правки довідника кликати invalidateUnits(). */
import { useEffect, useState } from "react";
import { api } from "./api";

export interface Unit { id: number; name: string; full_name: string; sort_order: number; is_active: boolean; products_count?: number }

/* запасний список — якщо API недоступне, форма все одно має щось показати */
export const FALLBACK_UNITS = ["шт", "кг", "г", "л", "мл", "м", "см", "м²", "м³", "пог.м", "рулон", "упаковка",
  "комплект", "набір", "пара", "відро", "банка", "пляшечка", "туба", "мішок", "пачка", "лист", "день", "година", "послуга"];

let cache: string[] | null = null;
let inflight: Promise<string[]> | null = null;

export function loadUnits(): Promise<string[]> {
  if (cache) return Promise.resolve(cache);
  if (!inflight) {
    inflight = api.get<Unit[]>("/api/units/")
      .then((rows) => { cache = (rows || []).map((u) => u.name).filter(Boolean); if (!cache.length) cache = FALLBACK_UNITS; return cache; })
      .catch(() => { cache = FALLBACK_UNITS; return cache; })
      .finally(() => { inflight = null; });
  }
  return inflight;
}

export function invalidateUnits() { cache = null; }

export function useUnits(): string[] {
  const [u, setU] = useState<string[]>(cache || FALLBACK_UNITS);
  useEffect(() => { let ok = true; loadUnits().then((x) => { if (ok) setU(x); }); return () => { ok = false; }; }, []);
  return u;
}
