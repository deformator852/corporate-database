/** Short absolute date and time in the UI language. */
export function formatDateTime(value: string, locale?: string): string {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }
    return new Intl.DateTimeFormat(locale, {
        dateStyle: "medium",
        timeStyle: "short",
    }).format(date);
}

const RELATIVE_STEPS: [Intl.RelativeTimeFormatUnit, number][] = [
    ["second", 60],
    ["minute", 60],
    ["hour", 24],
    ["day", 7],
    ["week", 4.35],
    ["month", 12],
    ["year", Number.POSITIVE_INFINITY],
];

/** "2 minutes ago", "yesterday" in the UI language. */
export function formatRelativeTime(value: string, locale?: string, now = Date.now()): string {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }
    let amount = (date.getTime() - now) / 1000;
    for (const [unit, size] of RELATIVE_STEPS) {
        if (Math.abs(amount) < size) {
            return new Intl.RelativeTimeFormat(locale, {numeric: "auto"}).format(
                Math.round(amount),
                unit,
            );
        }
        amount /= size;
    }
    return formatDateTime(value, locale);
}

