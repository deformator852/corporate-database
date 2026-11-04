import {screen, within} from "@testing-library/react";
import {describe, expect, it, vi} from "vitest";

import {renderApp, sessionUser} from "@/test/app";

// An extension with its own themes, as in src/custom/.
vi.mock("@/extensions", async (original) => ({
    ...(await original<typeof import("@/extensions")>()),
    extensions: [
        {
            themes: [
                {id: "ocean", labelKey: "custom.theme.ocean"},
                {id: "graphite", labelKey: "custom.theme.graphite", dark: true},
            ],
            defaultTheme: "ocean",
        },
    ],
}));

describe("Themes from an extension", () => {
    it("start on the extension's default and remember the chosen one", async () => {
        const {user} = renderApp("/", sessionUser());
        const picker = await screen.findByRole("button", {name: /^Theme:/});
        expect(document.documentElement.dataset.theme).toBe("ocean");

        await user.click(picker);
        const themes = within(await screen.findByRole("radiogroup", {name: "Theme"}));
        expect(themes.getAllByRole("radio").map((option) => option.textContent)).toEqual(["Corporate", "Dark", "custom.theme.ocean", "custom.theme.graphite"]);

        await user.click(themes.getByRole("radio", {name: "custom.theme.graphite"}));
        expect(document.documentElement.dataset.theme).toBe("graphite");
        expect(document.documentElement).toHaveClass("dark");
        expect(localStorage.getItem("ui-theme")).toBe("graphite");
    });
});
