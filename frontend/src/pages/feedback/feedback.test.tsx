import {screen, waitFor} from "@testing-library/react";
import {describe, expect, it} from "vitest";

import {renderApp, sessionUser} from "@/test/app";

const RATED = {
    message_id: 12,
    rating: "down",
    question: "What is the travel budget?",
    answer: "I don't know.",
    sources: [{id: 3, name: "Travel policy", filename: "policy.pdf"}],
    rated_at: "2026-10-07T09:00:00Z",
    user: {id: 5, name: "Ana López", email: "ana@acme.io"},
};

describe("Answer ratings", () => {
    it("lists bad answers with their questions and switches to good ones", async () => {
        const {user, server} = renderApp("/feedback", sessionUser(["chat.feedback"]), (s) =>
            s.on("GET", "/chat/feedback", (req) =>
                req.params.rating === "up"
                    ? {items: [], page: 1, per_page: 20, total: 0, pages: 0}
                    : {items: [RATED], page: 1, per_page: 20, total: 1, pages: 1},
            ),
        );

        expect(await screen.findByText("What is the travel budget?")).toBeInTheDocument();
        expect(screen.getByText("I don't know.")).toBeInTheDocument();
        expect(screen.getByText(/Ana López/)).toBeInTheDocument();
        expect(screen.getByRole("button", {name: "Open Travel policy"})).toBeInTheDocument();

        await user.selectOptions(screen.getByRole("combobox", {name: "Show"}), "up");
        expect(await screen.findByText("No answers rated yet")).toBeInTheDocument();
        await waitFor(() => expect(server.sent("GET", "/chat/feedback").at(-1)?.params).toMatchObject({rating: "up"}));
    });

    it("is not there without the permission", async () => {
        renderApp("/feedback", sessionUser([]), (s) => s.on("GET", "/chat/feedback", {items: [], total: 0}));
        expect(await screen.findByRole("heading", {name: "Page not found"})).toBeInTheDocument();
    });
});
