export const MAX_DOCUMENT_BYTES = 32 * 1024 * 1024;
export const DOCUMENTS_PER_PAGE = 20;

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

export const DOCUMENT_STATUSES = [
    "queued",
    "parsing",
    "chunking",
    "embedding",
    "completed",
    "failed",
] as const;

export type DocumentStatus = (typeof DOCUMENT_STATUSES)[number];

export const DOCUMENT_CLASSIFICATIONS = [
    "standard",
    "restricted",
    "confidential",
    "secret",
] as const;

export type DocumentClassification = (typeof DOCUMENT_CLASSIFICATIONS)[number];

export const DOCUMENT_CLASSIFICATION_LABELS: Record<DocumentClassification, string> = {
    standard: "Standard",
    restricted: "Restricted",
    confidential: "Confidential",
    secret: "Secret",
};

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

export const DOCUMENT_STATUS_LABELS: Record<DocumentStatus, string> = {
    queued: "Queued",
    parsing: "Parsing",
    chunking: "Chunking",
    embedding: "Embedding",
    completed: "Completed",
    failed: "Failed",
};

export const DOCUMENT_STATUS_RANK: Record<DocumentStatus, number> = {
    queued: 0,
    parsing: 1,
    chunking: 2,
    embedding: 3,
    completed: 4,
    failed: 4,
};

export function isDocumentStatus(value: string): value is DocumentStatus {
    return (DOCUMENT_STATUSES as readonly string[]).includes(value);
}

export function isDocumentClassification(
    value: string,
): value is DocumentClassification {
    return (DOCUMENT_CLASSIFICATIONS as readonly string[]).includes(value);
}

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
