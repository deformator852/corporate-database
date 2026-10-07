import {z} from "zod";

import type {TranslateFn} from "@/shared/i18n/I18nProvider";
import type {MessageKey} from "@/shared/i18n/messages";

/** Periods back from now, in days; "all" and "custom" have none. */
const PRESET_DAYS = {day: 1, "3days": 3, week: 7, month: 30, year: 365} as const;

export const PURGE_PERIODS = ["day", "3days", "week", "month", "year", "all", "custom"] as const;
export type PurgePeriod = (typeof PURGE_PERIODS)[number];

export function purgePeriodKey(period: PurgePeriod): MessageKey {
    return `chatPurge.period.${period}` as MessageKey;
}

/** Chats last active in [since, until) are deleted; null leaves an end open. */
export type PurgeRange = {since: string | null; until: string | null};

export function createPurgeSchema(t: TranslateFn) {
    return z
        .object({
            period: z.enum(PURGE_PERIODS),
            // yyyy-mm-dd from <input type="date">, used by "custom" only.
            from: z.string(),
            to: z.string(),
        })
        .refine((data) => data.period !== "custom" || (data.from && data.to), {
            path: ["to"],
            message: t("chatPurge.chooseDates"),
        })
        .refine((data) => data.period !== "custom" || !data.from || !data.to || data.from <= data.to, {
            path: ["to"],
            message: t("chatPurge.datesOrder"),
        });
}

export type PurgeFormData = z.infer<ReturnType<typeof createPurgeSchema>>;

/** The range a choice means; dates are whole local days, both included. */
export function purgeRange({period, from, to}: PurgeFormData, now = new Date()): PurgeRange {
    if (period === "all") {
        return {since: null, until: null};
    }
    if (period === "custom") {
        const end = localDay(to);
        end.setDate(end.getDate() + 1);
        return {since: localDay(from).toISOString(), until: end.toISOString()};
    }
    const since = new Date(now);
    since.setDate(since.getDate() - PRESET_DAYS[period]);
    return {since: since.toISOString(), until: null};
}

function localDay(value: string): Date {
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day);
}
