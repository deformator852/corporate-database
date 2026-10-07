import {api} from "@/shared/lib/api/client";

// Shown in a browser tab; every other type downloads.
const PREVIEW_TYPES: Record<string, string> = {
    pdf: "application/pdf",
    txt: "text/plain;charset=utf-8",
    md: "text/plain;charset=utf-8",
    mdx: "text/plain;charset=utf-8",
    csv: "text/plain;charset=utf-8",
};

/** A passage of a document as search stores it; `page` for PDFs. */
export type DocumentChunk = {text: string; page: number | null};

/** The passage `index` of a document (a chat source's `chunk`). */
export async function getDocumentChunk(id: number, index: number): Promise<DocumentChunk> {
    const {data} = await api.get<DocumentChunk>(`/documents/${id}/chunks/${index}`);
    return data;
}

function extension(filename: string): string {
    return filename.split(".").pop()?.toLowerCase() ?? "";
}

/**
 * Opens a document the user may read: PDF and text in a new tab, anything
 * else as a download. Fetched through the API client (so an expired session
 * refreshes); the tab opens synchronously inside the click, before awaiting,
 * or popup blockers stop it. The preview blob is typed PDF or plain text only,
 * never HTML, so a file cannot run script in the app's origin.
 */
export async function openDocumentFile(id: number, filename: string, page?: number | null): Promise<void> {
    const previewType = PREVIEW_TYPES[extension(filename)];
    const tab = previewType ? window.open("about:blank", "_blank") : null;
    try {
        const {data} = await api.get<Blob>(`/documents/${id}/file`, {responseType: "blob"});
        const blob = previewType ? new Blob([data], {type: previewType}) : data;
        const url = URL.createObjectURL(blob);
        if (tab) {
            // Browsers' PDF viewers open at #page=N.
            tab.location.href = page != null && extension(filename) === "pdf" ? `${url}#page=${page}` : url;
        } else {
            const link = document.createElement("a");
            link.href = url;
            link.download = filename;
            link.click();
        }
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (error) {
        tab?.close();
        throw error;
    }
}
