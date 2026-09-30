import {screen, within} from "@testing-library/react";
import {describe, expect, it} from "vitest";

import {mergeByKey} from "@/extensions";
import {en, messages} from "@/shared/i18n/messages";
import {keyFromName} from "@/shared/lib/keyFromName";
import {formatDateTime, formatRelativeTime} from "@/shared/lib/time";
import {reconnectDelay} from "@/shared/lib/ws";
import {allowedUploadClassifications, fileStem, isDocumentUpdateNewer, type DocumentListItem} from "@pages/documents/model/documents";
import {AUDIT_ACTIONS, auditActionKey} from "@pages/audit/model/audit";
import {mockApi, reply} from "@/test/api";
import {renderApp, sessionUser} from "@/test/app";

describe("Translations", () => {
    const placeholders = (text: string) => [...text.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort();

    it.each(["es", "fr"] as const)("%s has every English text, with the same placeholders", (locale) => {
        for (const [key, text] of Object.entries(en)) {
            const translated = messages[locale][key as keyof typeof en];
            expect(translated, key).toBeTruthy();
            expect(placeholders(translated), key).toEqual(placeholders(text));
        }
    });

    it("names every audit action", () => {
        for (const action of AUDIT_ACTIONS) {
            expect(en[auditActionKey(action) as keyof typeof en], action).toBeTruthy();
        }
    });
});

describe("Formatting and rules", () => {
    it("formats times relative to now", () => {
        const now = Date.parse("2026-09-30T12:00:00Z");
        expect(formatRelativeTime("2026-09-30T11:58:00Z", "en", now)).toBe("2 minutes ago");
        expect(formatRelativeTime("2026-09-29T12:00:00Z", "en", now)).toBe("yesterday");
        expect(formatRelativeTime("garbage", "en", now)).toBe("garbage");
        expect(formatDateTime("garbage")).toBe("garbage");
    });

    it.each([
        ["Legal team", "legal.team"],
        ["  HR / Payroll ", "hr.payroll"],
        ["1st line", null],
        ["!", null],
        ["x".repeat(60), null],
    ])("role key of %j is %j", (name, key) => {
        expect(keyFromName(name)).toBe(key);
    });

    it("offers upload levels up to the user's clearance", () => {
        expect(allowedUploadClassifications(false, false, false)).toEqual(["standard"]);
        expect(allowedUploadClassifications(false, false, true)).toEqual(["standard", "restricted", "confidential", "secret"]);
        expect(fileStem("Q3 report.final.pdf")).toBe("Q3 report.final");
    });

    it("ignores document events older than what is shown", () => {
        const doc = (status: DocumentListItem["status"], progress: number) => ({status, progress}) as DocumentListItem;
        expect(isDocumentUpdateNewer(doc("embedding", 70), doc("parsing", 15))).toBe(true);
        expect(isDocumentUpdateNewer(doc("parsing", 15), doc("embedding", 70))).toBe(false);
        expect(isDocumentUpdateNewer(doc("embedding", 60), doc("completed", 100))).toBe(false);
        expect(isDocumentUpdateNewer(doc("queued", 0), doc("failed", 30))).toBe(false);
        expect(isDocumentUpdateNewer(doc("completed", 100), doc("failed", 30))).toBe(true);  // processed again
    });

    it("lets customizations replace core items by key", () => {
        const core = [{to: "/", label: "Home"}, {to: "/docs", label: "Docs"}];
        const merged = mergeByKey(core, [{to: "/docs", label: "Library"}, {to: "/kb", label: "KB"}], (i) => i.to);
        expect(merged.map((i) => i.label)).toEqual(["Home", "Library", "KB"]);
    });
});

describe("Socket reconnects", () => {
    it("waits longer after losing access, and renews an ended session first", async () => {
        const server = mockApi().on("POST", "/auth/refresh");
        expect(await reconnectDelay(4403)).toBe(30_000);
        expect(await reconnectDelay(1006)).toBe(2000);
        expect(await reconnectDelay(4401)).toBe(0);
        expect(server.sent("POST", "/auth/refresh")).toHaveLength(1);
        server.on("POST", "/auth/refresh", reply(401));
        expect(await reconnectDelay(4401)).toBeNull();
    });
});

describe("App shell", () => {
    it("remembers the chosen theme", async () => {
        const {user} = renderApp("/", sessionUser());
        await user.click(await screen.findByRole("button", {name: /^Theme:/}));
        await user.click(within(await screen.findByRole("radiogroup", {name: "Theme"})).getByRole("radio", {name: "Midnight"}));
        expect(document.documentElement.dataset.theme).toBe("midnight");
        expect(document.documentElement).toHaveClass("dark");
        expect(localStorage.getItem("ui-theme")).toBe("midnight");
    });

    it("shows a not-found page for unknown addresses", async () => {
        const {user, router} = renderApp("/no/such/page", sessionUser());
        expect(await screen.findByRole("heading", {level: 1})).toBeInTheDocument();
        await user.click(screen.getByRole("link", {name: en["notFound.backHome"]}));
        expect(router.state.location.pathname).toBe("/");
    });
});
