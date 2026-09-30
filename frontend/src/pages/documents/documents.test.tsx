import {act, screen, waitFor, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {describe, expect, it, vi} from "vitest";

import {apiError, type MockApi} from "@/test/api";
import {renderApp, sessionUser} from "@/test/app";
import {FakeWebSocket} from "@/test/socket";

const WRITER = ["documents.list", "documents.create", "documents.delete"];

type Doc = {id: number; name: string; filename: string; status?: string; progress?: number; classification?: string; error_message?: string | null};

function documents(server: MockApi, list: Doc[]) {
    server.on("GET", "/documents", () => ({
        items: list.map((d) => ({status: "completed", progress: 100, classification: "standard", error_message: null, created_at: "2026-09-30T10:00:00Z", ...d})),
        page: 1, per_page: 20, total: list.length, pages: 1,
    }));
}

const POLICY: Doc = {id: 1, name: "Travel policy", filename: "policy.pdf"};

function row(name: string): HTMLElement {
    return screen.getByRole("button", {name}).closest("tr") as HTMLElement;
}

describe("Documents page", () => {
    it("lists documents with access level, status and failure reason", async () => {
        renderApp("/documents", sessionUser(WRITER), (s) =>
            documents(s, [POLICY, {id: 2, name: "Scan", filename: "scan.pdf", status: "failed", progress: 15, classification: "secret", error_message: "The document has no text."}]),
        );

        const failed = row(await screen.findByText("Scan").then((el) => el.textContent ?? ""));
        expect(within(failed).getByText("Secret")).toBeInTheDocument();
        expect(within(failed).getByText("Failed")).toBeInTheDocument();
        expect(within(failed).getByText("The document has no text.")).toBeInTheDocument();
        expect(within(failed).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "15");
    });

    it("uploads a file: the name comes from the file, access is limited by clearance", async () => {
        const {user, server} = renderApp("/documents", sessionUser([...WRITER, "documents.confidential"]), (s) => {
            documents(s, []);
            s.on("POST", "/documents", {id: 9, name: "Budget 2026", filename: "Budget 2026.xlsx", status: "queued", progress: 0, classification: "confidential", error_message: null, created_at: "2026-09-30T10:00:00Z", converted: false});
        });

        const access = await screen.findByLabelText("Access");
        expect([...(access as HTMLSelectElement).options].map((o) => o.value)).toEqual(["standard", "restricted", "confidential"]);
        await user.upload(screen.getByLabelText("File"), new File(["x".repeat(10)], "Budget 2026.xlsx"));
        expect(screen.getByLabelText("Name")).toHaveValue("Budget 2026");
        await user.selectOptions(access, "confidential");
        await user.click(screen.getByRole("button", {name: "Upload"}));

        expect(await screen.findByText("Document uploaded.")).toBeInTheDocument();
        const form = server.sent("POST", "/documents")[0].body as FormData;
        expect(form.get("name")).toBe("Budget 2026");
        expect(form.get("classification")).toBe("confidential");
        expect((form.get("file") as File).name).toBe("Budget 2026.xlsx");
        expect(await screen.findByText("Queued")).toBeInTheDocument();
    });

    it("refuses files it cannot process before uploading", async () => {
        const {server} = renderApp("/documents", sessionUser(WRITER), (s) => documents(s, []));
        // A drag-and-drop or "all files" pick bypasses the input's accept list.
        const user = userEvent.setup({applyAccept: false});
        await user.upload(await screen.findByLabelText("File"), new File(["#!"], "run.sh"));
        await user.click(screen.getByRole("button", {name: "Upload"}));
        expect(await screen.findByText("This file type is not supported.")).toBeInTheDocument();
        expect(server.sent("POST", "/documents")).toHaveLength(0);
    });

    it("shows the server's reason when an upload fails", async () => {
        const {user} = renderApp("/documents", sessionUser(WRITER), (s) => {
            documents(s, []);
            s.on("POST", "/documents", apiError(400, "The file content does not match its type."));
        });
        await user.upload(await screen.findByLabelText("File"), new File(["MZ"], "fake.pdf"));
        await user.click(screen.getByRole("button", {name: "Upload"}));
        expect(await screen.findByRole("alert")).toHaveTextContent("The file content does not match its type.");
    });

    it("updates progress live and never moves a document backwards", async () => {
        renderApp("/documents", sessionUser(WRITER), (s) => documents(s, [{...POLICY, status: "queued", progress: 0}]));
        await screen.findByText("Queued");
        const socket = await waitFor(() => FakeWebSocket.at("/api/v1/documents/ws"));

        const event = (status: string, progress: number) => ({...POLICY, status, progress, classification: "standard", error_message: null, created_at: "2026-09-30T10:00:00Z"});
        act(() => socket.receive(event("embedding", 70)));
        expect(await screen.findByText("Embedding")).toBeInTheDocument();
        act(() => socket.receive(event("parsing", 15)));  // late, out-of-order event
        expect(screen.getByText("Embedding")).toBeInTheDocument();
        act(() => socket.receive(event("completed", 100)));
        expect(await screen.findByText("Completed")).toBeInTheDocument();
    });

    it("opens a PDF in a new tab", async () => {
        const tab = {location: {href: ""}, close: vi.fn()};
        vi.spyOn(window, "open").mockReturnValue(tab as unknown as Window);
        URL.createObjectURL = vi.fn(() => "blob:policy");
        URL.revokeObjectURL = vi.fn();
        const {user, server} = renderApp("/documents", sessionUser(WRITER), (s) => {
            documents(s, [POLICY]);
            s.on("GET", "/documents/:id/file", new Blob(["%PDF"]));
        });

        await user.click(await screen.findByRole("button", {name: "Travel policy"}));

        await waitFor(() => expect(tab.location.href).toBe("blob:policy"));
        expect(server.sent("GET", "/documents/1/file")).toHaveLength(1);
    });

    it("explains when a document cannot be opened", async () => {
        const tab = {location: {href: ""}, close: vi.fn()};
        vi.spyOn(window, "open").mockReturnValue(tab as unknown as Window);
        const {user} = renderApp("/documents", sessionUser(WRITER), (s) => {
            documents(s, [POLICY]);
            s.on("GET", "/documents/:id/file", apiError(503, "The document file is missing.", "not_found"));
        });
        await user.click(await screen.findByRole("button", {name: "Travel policy"}));
        expect(await screen.findByRole("alert")).toHaveTextContent("The document file is missing.");
        expect(tab.close).toHaveBeenCalled();
    });

    it("deletes a document after confirmation", async () => {
        const list = [POLICY];
        const {user} = renderApp("/documents", sessionUser(WRITER), (s) => {
            documents(s, list);
            s.on("DELETE", "/documents/:id", () => {
                list.pop();
                return {};
            });
        });
        await user.click(await screen.findByRole("button", {name: "Delete Travel policy?"}));
        await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", {name: "Delete"}));
        await waitFor(() => expect(screen.queryByText("Travel policy")).not.toBeInTheDocument());
    });

    it("hides upload and delete from readers", async () => {
        renderApp("/documents", sessionUser(["documents.list"]), (s) => documents(s, [POLICY]));
        await screen.findByText("Travel policy");
        expect(screen.queryByLabelText("File")).not.toBeInTheDocument();
        expect(screen.queryByRole("button", {name: "Delete Travel policy?"})).not.toBeInTheDocument();
    });
});
