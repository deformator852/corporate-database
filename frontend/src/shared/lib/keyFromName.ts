const KEY_MAX_LENGTH = 50;

const NON_KEY = /[^a-z0-9]+/g;

export function keyFromName(name: string): string | null {
    const cleaned = name
        .trim()
        .toLowerCase()
        .replace(NON_KEY, ".")
        .replace(/^\.+|\.+$/g, "");
    if (cleaned.length < 2 || cleaned.length > KEY_MAX_LENGTH) {
        return null;
    }
    if (cleaned[0] < "a" || cleaned[0] > "z") {
        return null;
    }
    return cleaned;
}
