import type {TranslateFn} from "@/shared/i18n/I18nProvider";
import {documentClassificationKey} from "@/entities/document/model";
import type {DocumentClassification} from "@/entities/document/model";
import {auditActionKey, isKnownAction, type AuditEntry} from "@/entities/audit/model";

export function actionLabel(t: TranslateFn, action: string): string {
    return isKnownAction(action) ? t(auditActionKey(action)) : action;
}

function list(value: unknown): string[] {
    return Array.isArray(value) ? value.map(String) : [];
}

function accessLabel(t: TranslateFn, value: unknown): string {
    return t(documentClassificationKey(String(value) as DocumentClassification));
}

/** Short human summary of the structured `details` of an entry. */
export function describe(t: TranslateFn, entry: AuditEntry): string {
    const {details} = entry;
    const parts: string[] = [];
    if (details.password_changed === true) {
        parts.push(t("audit.details.passwordChanged"));
    }
    const roles = list(details.roles);
    if (roles.length > 0) {
        parts.push(t("audit.details.roles", {value: roles.join(", ")}));
    }
    const permissions = list(details.permissions);
    if (permissions.length > 0) {
        parts.push(t("audit.details.permissions", {value: permissions.join(", ")}));
    }
    if (typeof details.classification === "string") {
        parts.push(t("audit.details.access", {value: accessLabel(t, details.classification)}));
    }
    // A document edit: what it was before.
    if (typeof details.previous_name === "string" && details.previous_name !== entry.target_label) {
        parts.push(t("audit.details.previousName", {value: details.previous_name}));
    }
    if (
        typeof details.previous_classification === "string" &&
        details.previous_classification !== details.classification
    ) {
        parts.push(t("audit.details.previousAccess", {value: accessLabel(t, details.previous_classification)}));
    }
    // Cleared chat history: the period and how many chats went.
    if (typeof details.deleted === "number") {
        const day = (value: unknown) => (typeof value === "string" ? new Date(value).toLocaleDateString() : "…");
        parts.push(
            details.since == null && details.until == null
                ? t("audit.details.allTime")
                : t("audit.details.period", {from: day(details.since), to: day(details.until)}),
        );
        parts.push(t("audit.details.deletedChats", {count: details.deleted}));
    }
    if (typeof details.documents === "number") {
        parts.push(t("audit.details.documentCount", {count: details.documents}));
    }
    if (Array.isArray(details.documents)) {
        const documents = details.documents as {name?: unknown; classification?: unknown}[];
        parts.push(
            documents
                .map((doc) => `${String(doc.name)} (${accessLabel(t, doc.classification)})`)
                .join(", "),
        );
    }
    return parts.join(" · ");
}
