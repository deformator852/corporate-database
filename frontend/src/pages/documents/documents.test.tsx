import {act, screen, waitFor, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {describe, expect, it, vi} from "vitest";

import {apiError, type MockApi} from "@/test/api";
import {renderApp, sessionUser} from "@/test/app";
import {FakeWebSocket} from "@/test/socket";

const WRITER = ["documents.list", "documents.create", "documents.delete"];

type Doc = {id: number; name: string; filename: string; status?: string; progress?: number; classification?: string; error_message?: string | null; file_missing?: boolean};

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

    it("marks documents whose file is not in the storage", async () => {
        renderApp("/documents", sessionUser(WRITER), (s) => documents(s, [POLICY, {id: 2, name: "Contract", filename: "contract.pdf", file_missing: true}]));

        const missing = row(await screen.findByText("Contract").then((el) => el.textContent ?? ""));
        expect(within(missing).getByText("The file is not in the storage.")).toBeInTheDocument();
        expect(within(row("Travel policy")).queryByText("The file is not in the storage.")).not.toBeInTheDocument();
    });

    it("loads the list again after the live connection was down", async () => {
        const {server} = renderApp("/documents", sessionUser(WRITER), (s) => documents(s, [{...POLICY, status: "embedding", progress: 70}]));
        await screen.findByText("Embedding");
        const socket = await waitFor(() => FakeWebSocket.at("/api/v1/documents/ws"));
        // Finished while the socket was down: its event never arrives.
        documents(server, [POLICY]);

        act(() => socket.close(4401));

        expect(await screen.findByText("Completed")).toBeInTheDocument();
    });

    it("processes a failed document again", async () => {
        const scan: Doc = {id: 2, name: "Scan", filename: "scan.pdf", status: "failed", progress: 15, error_message: "The document has no text."};
        const {user, server} = renderApp("/documents", sessionUser(WRITER), (s) => {
            documents(s, [scan, POLICY]);
            s.on("POST", "/documents/:id/retry", () => {
                documents(server, [POLICY, {...scan, status: "queued", progress: 0, error_message: null}]);
                return {...scan, status: "queued", progress: 0, classification: "standard", error_message: null, created_at: "2026-09-30T10:00:00Z"};
            });
        });

        await screen.findByText("Scan");
        expect(within(row("Travel policy")).queryByRole("button", {name: /Process/})).toBeNull();
        await user.click(screen.getByRole("button", {name: "Process Scan again"}));

        await waitFor(() => expect(server.sent("POST", "/documents/2/retry")).toHaveLength(1));
        expect(await screen.findByText("Queued")).toBeInTheDocument();
        expect(screen.queryByText("The document has no text.")).not.toBeInTheDocument();
    });

    it("renames a document and changes its access level", async () => {
        const {user, server} = renderApp("/documents", sessionUser([...WRITER, "documents.update", "documents.confidential"]), (s) => {
            documents(s, [POLICY]);
            s.on("PATCH", "/documents/:id", (request) => ({
                ...POLICY,
                ...(request.body as object),
                status: "completed",
                progress: 100,
                error_message: null,
                created_at: "2026-09-30T10:00:00Z",
            }));
        });

        await user.click(await screen.findByRole("button", {name: "Edit Travel policy"}));
        const dialog = await screen.findByRole("dialog", {name: "Edit document"});
        await user.clear(within(dialog).getByLabelText("Name"));
        await user.type(within(dialog).getByLabelText("Name"), "Trips");
        await user.selectOptions(within(dialog).getByLabelText("Access"), "confidential");
        await user.click(within(dialog).getByRole("button", {name: "Save changes"}));

        await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
        expect(server.sent("PATCH", "/documents/1")[0].body).toEqual({name: "Trips", classification: "confidential"});
        expect(within(row("Trips")).getByText("Confidential")).toBeInTheDocument();
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
        expect(await within(screen.getByRole("table")).findByText("Completed")).toBeInTheDocument();
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

describe("Document filters", () => {
    it("searches and filters on the server and offers to clear an empty result", async () => {
        const {user, server} = renderApp("/documents", sessionUser(WRITER), (s) => {
            s.on("GET", "/documents", (req) =>
                req.params.q || req.params.status
                    ? {items: [], page: 1, per_page: 20, total: 0, pages: 0}
                    : {items: [{...POLICY, status: "completed", progress: 100, classification: "standard", error_message: null, created_at: "2026-09-30T10:00:00Z"}], page: 1, per_page: 20, total: 1, pages: 1},
            );
        });
        await screen.findByText("Travel policy");

        await user.type(screen.getByRole("searchbox", {name: "Search by name or file"}), "budget");
        await user.selectOptions(screen.getByRole("combobox", {name: "Filter by status"}), "failed");

        expect(await screen.findByText("No documents match these filters")).toBeInTheDocument();
        await waitFor(() =>
            expect(server.sent("GET", "/documents").at(-1)?.params).toMatchObject({q: "budget", status: "failed"}),
        );
        await user.click(screen.getByRole("button", {name: "Clear filters"}));
        expect(await screen.findByText("Travel policy")).toBeInTheDocument();
        expect(screen.getByRole("searchbox", {name: "Search by name or file"})).toHaveValue("");
    });
});

describe("Uploading several files", () => {
    function accept(id: number, form: FormData) {
        const file = form.get("file") as File;
        if (file.name === "fake.pdf") {
            return apiError(400, "The file content does not match its type.");
        }
        return {id, name: form.get("name"), filename: file.name, status: "queued", progress: 0, classification: "standard", error_message: null, created_at: "2026-09-30T10:00:00Z", converted: false};
    }

    it("uploads each file under its own name and keeps the ones that failed", async () => {
        let id = 10;
        const {user, server} = renderApp("/documents", sessionUser(WRITER), (s) => {
            documents(s, []);
            s.on("POST", "/documents", (req) => accept(id++, req.body as FormData));
        });
        await user.upload(await screen.findByLabelText("File"), [
            new File(["a"], "Budget.xlsx"),
            new File(["MZ"], "fake.pdf"),
            new File(["b"], "Travel policy.txt"),
        ]);
        expect(screen.getByText("3 files selected")).toBeInTheDocument();
        expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();  // named after the files

        await user.click(screen.getByRole("button", {name: "Upload"}));

        expect(await screen.findByRole("alert")).toHaveTextContent("1 of 3 files were not uploaded.");
        const names = server.sent("POST", "/documents").map((r) => (r.body as FormData).get("name"));
        expect(names).toEqual(["Budget", "fake", "Travel policy"]);
        const left = screen.getByRole("listitem");  // only the failed file stays
        expect(left).toHaveTextContent("fake.pdf");
        expect(left).toHaveTextContent("The file content does not match its type.");
        expect(await screen.findAllByText("Queued")).toHaveLength(2);
    });

    it("checks every file before sending any and lets one be removed", async () => {
        const {server} = renderApp("/documents", sessionUser(WRITER), (s) => {
            documents(s, []);
            s.on("POST", "/documents", (req) => accept(10, req.body as FormData));
        });
        const user = userEvent.setup({applyAccept: false});
        await user.upload(await screen.findByLabelText("File"), [new File(["a"], "notes.txt"), new File(["#!"], "run.sh"), new File(["b"], "plan.md")]);
        await user.click(screen.getByRole("button", {name: "Upload"}));
        expect(await screen.findByText("This file type is not supported.")).toBeInTheDocument();
        expect(server.sent("POST", "/documents")).toHaveLength(0);

        await user.click(screen.getByRole("button", {name: "Remove run.sh"}));
        await user.click(screen.getByRole("button", {name: "Upload"}));
        expect(await screen.findByText("2 documents uploaded.")).toBeInTheDocument();
        expect(server.sent("POST", "/documents")).toHaveLength(2);
    });
});

describe("Upload limits", () => {
    it("takes at most 50 files at a time", async () => {
        const {user, server} = renderApp("/documents", sessionUser(WRITER), (s) => documents(s, []));
        const files = Array.from({length: 51}, (_, i) => new File(["x"], `note ${i}.txt`));
        await user.upload(await screen.findByLabelText("File"), files);
        await user.click(screen.getByRole("button", {name: "Upload"}));
        expect(await screen.findByText("Choose up to 50 files at a time.")).toBeInTheDocument();
        expect(server.sent("POST", "/documents")).toHaveLength(0);
    });

    it("stops sending once the server says too many documents wait", async () => {
        const busy = "Too many of your documents are waiting to be processed. Upload more when some are ready.";
        const {user, server} = renderApp("/documents", sessionUser(WRITER), (s) => {
            documents(s, []);
            s.on("POST", "/documents", () => apiError(429, busy, "rate_limited"));
        });
        await user.upload(await screen.findByLabelText("File"), [new File(["a"], "a.txt"), new File(["b"], "b.txt"), new File(["c"], "c.txt")]);
        await user.click(screen.getByRole("button", {name: "Upload"}));

        expect(await screen.findByRole("alert")).toHaveTextContent("3 of 3 files were not uploaded.");
        expect(server.sent("POST", "/documents")).toHaveLength(1);
        expect(screen.getAllByText(busy)).toHaveLength(3);
    });
});

describe("Upload name after a failed upload", () => {
    it("takes the next file's name instead of keeping the rejected one", async () => {
        const {user} = renderApp("/documents", sessionUser(WRITER), (s) => {
            documents(s, []);
            s.on("POST", "/documents", apiError(400, "The file content does not match its type."));
        });
        await user.upload(await screen.findByLabelText("File"), new File(["MZ"], "fake.pdf"));
        await user.click(screen.getByRole("button", {name: "Upload"}));
        await screen.findByRole("alert");
        await user.upload(screen.getByLabelText("File"), new File(["text"], "policy.txt"));
        expect(screen.getByLabelText("Name")).toHaveValue("policy");
        await user.clear(screen.getByLabelText("Name"));
        await user.type(screen.getByLabelText("Name"), "Travel policy");
        await user.upload(screen.getByLabelText("File"), new File(["text"], "other.txt"));
        expect(screen.getByLabelText("Name")).toHaveValue("Travel policy");  // a typed name stays
    });
});
