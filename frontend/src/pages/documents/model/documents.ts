import {
    isDocumentClassification,
    isDocumentStatus,
    type DocumentClassification,
    type DocumentStatus,
} from "@/entities/document/model";

export const MAX_DOCUMENT_BYTES = 32 * 1024 * 1024;
/** Files per upload, so a whole folder dropped by mistake is caught at once.
 * The server also limits each user's documents waiting to be processed. */
export const MAX_UPLOAD_FILES = 50;
export const DOCUMENTS_PER_PAGE = 20;

/** "processing": queued or any processing step. */
export const DOCUMENT_STATUS_FILTERS = ["processing", "completed", "failed"] as const;
export type DocumentStatusFilter = (typeof DOCUMENT_STATUS_FILTERS)[number];

/** What the list shows; empty values filter nothing. */
export type DocumentFilters = {
    query: string;
    status: DocumentStatusFilter | "";
    classification: DocumentClassification | "";
};

export const NO_FILTERS: DocumentFilters = {query: "", status: "", classification: ""};

export function isFiltered(filters: DocumentFilters): boolean {
    return Boolean(filters.query || filters.status || filters.classification);
}

export const DOCUMENT_EXTENSIONS = [
    ".pdf",
    ".docx",
    ".doc",
    ".txt",
    ".odt",
    ".xlsx",
    ".csv",
    ".xml",
    ".json",
    ".md",
    ".mdx",
] as const;

export const DOCUMENT_ACCEPT = DOCUMENT_EXTENSIONS.join(",");

export type DocumentListItem = {
    id: number;
    name: string;
    filename: string;
    status: DocumentStatus;
    progress: number;
    error_message: string | null;
    classification: DocumentClassification;
    created_at: string;
    converted?: boolean;
};

export type DocumentListPage = {
    items: DocumentListItem[];
    page: number;
    per_page: number;
    total: number;
    pages: number;
};

const DOCUMENT_STATUS_RANK: Record<DocumentStatus, number> = {
    queued: 0,
    parsing: 1,
    chunking: 2,
    embedding: 3,
    completed: 4,
    failed: 4,
};

export function allowedUploadClassifications(
    canRestricted: boolean,
    canConfidential: boolean,
    canSecret: boolean,
): DocumentClassification[] {
    const allowed: DocumentClassification[] = ["standard"];
    if (canRestricted || canConfidential || canSecret) {
        allowed.push("restricted");
    }
    if (canConfidential || canSecret) {
        allowed.push("confidential");
    }
    if (canSecret) {
        allowed.push("secret");
    }
    return allowed;
}

export function normalizeDocumentItem(
    item: Omit<DocumentListItem, "classification"> & {classification?: string},
): DocumentListItem {
    const classification = item.classification ?? "standard";
    return {
        ...item,
        classification: isDocumentClassification(classification)
            ? classification
            : "standard",
    };
}

export function isDocumentUpdateNewer(
    incoming: DocumentListItem,
    current: DocumentListItem,
): boolean {
    if (!isDocumentStatus(incoming.status) || !isDocumentStatus(current.status)) {
        return true;
    }
    // Queued again after a failure (Retry); only the retry announces "queued".
    if (current.status === "failed" && incoming.status === "queued") {
        return true;
    }
    if (current.status === "completed" && incoming.status !== "completed") {
        return false;
    }
    if (
        current.status === "failed" &&
        incoming.status !== "failed" &&
        incoming.status !== "completed"
    ) {
        return false;
    }
    const incomingRank = DOCUMENT_STATUS_RANK[incoming.status];
    const currentRank = DOCUMENT_STATUS_RANK[current.status];
    if (incomingRank !== currentRank) {
        return incomingRank > currentRank;
    }
    return incoming.progress >= current.progress;
}

/** Failed documents first, as the server lists them; the rest keep their order. */
export function failedFirst(items: DocumentListItem[]): DocumentListItem[] {
    return items.toSorted((a, b) => Number(b.status === "failed") - Number(a.status === "failed"));
}

export function fileExtension(filename: string): string {
    const index = filename.lastIndexOf(".");
    if (index < 0) {
        return "";
    }
    return filename.slice(index).toLowerCase();
}

export function fileStem(filename: string): string {
    const extension = fileExtension(filename);
    if (!extension) {
        return filename;
    }
    return filename.slice(0, -extension.length);
}
