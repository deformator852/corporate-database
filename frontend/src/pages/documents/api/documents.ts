import {api} from "@/shared/lib/api/client";
import {
    DOCUMENTS_PER_PAGE,
    normalizeDocumentItem,
    type DocumentListItem,
    type DocumentListPage,
} from "@pages/documents/model/documents";

export async function getDocumentsPage(
    page: number,
    perPage = DOCUMENTS_PER_PAGE,
): Promise<DocumentListPage> {
    const {data} = await api.get<DocumentListPage>("/documents", {
        params: {page, per_page: perPage},
    });
    return {
        ...data,
        items: data.items.map(normalizeDocumentItem),
    };
}

export async function uploadDocument(
    name: string,
    file: File,
    classification: DocumentListItem["classification"],
): Promise<DocumentListItem> {
    const body = new FormData();
    body.append("name", name);
    body.append("file", file);
    body.append("classification", classification);
    const {data} = await api.post<DocumentListItem>("/documents", body);
    return data;
}

export async function deleteDocument(documentId: number): Promise<void> {
    await api.delete(`/documents/${documentId}`);
}

export function documentsSocketUrl(): string {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/api/v1/documents/ws`;
}
