import {act, screen, waitFor} from "@testing-library/react";
import {describe, expect, it} from "vitest";

import {renderApp, sessionUser} from "@/test/app";
import {FakeWebSocket} from "@/test/socket";

describe("Search update banner", () => {
    it("follows the progress the server pushes, and goes when the update is over", async () => {
        renderApp("/documents", sessionUser());
        const socket = await waitFor(() => FakeWebSocket.at("/api/v1/system/reindex/ws"));
        expect(screen.queryByText(/Search is being updated/)).not.toBeInTheDocument();

        act(() => socket.receive({active: true, percent: 14}));
        expect(await screen.findByText(/Search is being updated \(14% done\)/)).toBeInTheDocument();

        act(() => socket.receive({active: true, percent: 92}));
        expect(await screen.findByText(/\(92% done\)/)).toBeInTheDocument();

        act(() => socket.receive({active: false, percent: 100}));
        await waitFor(() => expect(screen.queryByText(/Search is being updated/)).not.toBeInTheDocument());
    });
});
