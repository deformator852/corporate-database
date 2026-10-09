import {screen, waitFor} from "@testing-library/react";
import {afterEach, describe, expect, it} from "vitest";

import {renderApp, sessionUser} from "@/test/app";

const ALL = ["en", "es", "fr"] as const;

describe("Language switcher", () => {
    afterEach(() => localStorage.clear());

    it("shows the account's language and saves a new choice", async () => {
        const {user, server} = renderApp("/", sessionUser([], {language: "es"}), (s) => s.on("PUT", "/auth/language", {}), {
            locales: [...ALL],
        });

        await user.click(await screen.findByRole("button", {name: "Idioma: Español"}));
        expect(screen.getAllByRole("radio").map((option) => option.textContent)).toEqual(["English", "Español", "Français"]);
        await user.click(screen.getByRole("radio", {name: "Français"}));

        expect(await screen.findByRole("button", {name: "Langue: Français"})).toBeInTheDocument();
        expect(document.documentElement.lang).toBe("fr");
        expect(server.sent("PUT", "/auth/language").map((request) => request.body)).toEqual([{language: "fr"}]);
        // The server translates its messages to the language shown.
        expect(server.sent("PUT", "/auth/language")[0].headers["Accept-Language"]).toBe("fr");
    });

    it("offers only the enabled languages and saves the shown one on an account without a choice", async () => {
        const {user, server} = renderApp("/", sessionUser(), (s) => s.on("PUT", "/auth/language", {}), {locales: ["en", "fr"]});

        await user.click(await screen.findByRole("button", {name: "Language: English"}));
        expect(screen.getAllByRole("radio").map((option) => option.textContent)).toEqual(["English", "Français"]);
        await waitFor(() => expect(server.sent("PUT", "/auth/language").map((request) => request.body)).toEqual([{language: "en"}]));
    });

    it("is hidden with a single language", async () => {
        renderApp("/", sessionUser());
        expect(await screen.findByRole("button", {name: /Theme/})).toBeInTheDocument();
        expect(screen.queryByRole("button", {name: /Language/})).not.toBeInTheDocument();
    });
});
