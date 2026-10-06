import type {MessageKey} from "@/shared/i18n/messages";

const DOCUMENT_STATUSES = ["queued", "parsing", "chunking", "embedding", "completed", "failed"] as const;

export type DocumentStatus = (typeof DOCUMENT_STATUSES)[number];

/** Access levels, lowest first. */
export const DOCUMENT_CLASSIFICATIONS = ["standard", "restricted", "confidential", "secret"] as const;

export type DocumentClassification = (typeof DOCUMENT_CLASSIFICATIONS)[number];

export function isDocumentStatus(value: string): value is DocumentStatus {
    return (DOCUMENT_STATUSES as readonly string[]).includes(value);
}

export function isDocumentClassification(value: string): value is DocumentClassification {
    return (DOCUMENT_CLASSIFICATIONS as readonly string[]).includes(value);
}

export function documentClassificationKey(value: DocumentClassification): MessageKey {
    return `documents.classification.${value}` as MessageKey;
}

export function documentStatusKey(value: DocumentStatus): MessageKey {
    return `documents.status.${value}` as MessageKey;
}
