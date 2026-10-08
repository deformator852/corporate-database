import {screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";

import {renderApp, sessionUser} from "@/test/app";

describe("Search update banner", () => {
    it("tells every user how far the update is while it runs", async () => {
        renderApp("/documents", sessionUser(), (s) => s.on("GET", "/system/reindex", {active: true, percent: 40}));

        expect(await screen.findByText(/Search is being updated \(40% done\)/)).toBeInTheDocument();
    });

    it("stays hidden otherwise", async () => {
        const {server} = renderApp("/", sessionUser());

        await screen.findByRole("heading", {name: "Assistant"});
        expect(server.sent("GET", "/system/reindex")).toHaveLength(1);
        expect(screen.queryByText(/Search is being updated/)).not.toBeInTheDocument();
    });
});
