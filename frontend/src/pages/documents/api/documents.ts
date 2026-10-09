import {api} from "@/shared/lib/api/client";
import {
    DOCUMENTS_PER_PAGE,
    normalizeDocumentItem,
    type DocumentListItem,
    type DocumentListPage,
    NO_FILTERS,
    type DocumentFilters,
} from "@pages/documents/model/documents";
import {apiSocketUrl} from "@/shared/lib/ws";

export async function getDocumentsPage(
    page: number,
    filters: DocumentFilters = NO_FILTERS,
    perPage = DOCUMENTS_PER_PAGE,
): Promise<DocumentListPage> {
    const {data} = await api.get<DocumentListPage>("/documents", {
        params: {
            page,
            per_page: perPage,
            q: filters.query || undefined,
            status: filters.status || undefined,
            classification: filters.classification || undefined,
        },
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

export async function updateDocument(
    documentId: number,
    changes: Pick<DocumentListItem, "name" | "classification">,
): Promise<DocumentListItem> {
    const {data} = await api.patch<DocumentListItem>(`/documents/${documentId}`, changes);
    return normalizeDocumentItem(data);
}

/** Queues a failed document again. */
export async function retryDocument(documentId: number): Promise<DocumentListItem> {
    const {data} = await api.post<DocumentListItem>(`/documents/${documentId}/retry`);
    return normalizeDocumentItem(data);
}

export async function deleteDocument(documentId: number): Promise<void> {
    await api.delete(`/documents/${documentId}`);
}

export function documentsSocketUrl(): string {
    return apiSocketUrl("/documents/ws");
}
