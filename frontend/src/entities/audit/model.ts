import type {MessageKey} from "@/shared/i18n/messages";

export const AUDIT_PER_PAGE = 25;

// Core actions (backend models/audit.py). Extensions may log others; those
// show their raw action name.
export const AUDIT_ACTIONS = [
    "auth.login",
    "auth.login_failed",
    "auth.logout",
    "auth.password_change",
    "users.create",
    "users.update",
    "users.disable",
    "users.enable",
    "users.delete",
    "roles.create",
    "roles.update",
    "roles.delete",
    "documents.upload",
    "documents.update",
    "documents.retry",
    "documents.delete",
    "documents.view",
    "chat.answer",
    "chat.view",
    "chat.purge",
    "chat.delete",
    "chat.rating_delete",
    "system.rechunk",
] as const;

export type AuditAction = (typeof AUDIT_ACTIONS)[number];

export function isKnownAction(action: string): action is AuditAction {
    return (AUDIT_ACTIONS as readonly string[]).includes(action);
}

export function auditActionKey(action: AuditAction): MessageKey {
    return `audit.action.${action}` as MessageKey;
}

export type AuditEntry = {
    id: number;
    created_at: string;
    actor_id: number | null;
    actor_email: string | null;
    action: string;
    target_type: string | null;
    target_id: string | null;
    target_label: string | null;
    details: Record<string, unknown>;
    ip: string | null;
};

export type AuditListPage = {
    items: AuditEntry[];
    page: number;
    per_page: number;
    total: number;
    pages: number;
};

/** Infinite-scroll page: pass `next_cursor` as `before`; null means the end. */
export type AuditCursorPage = {
    items: AuditEntry[];
    next_cursor: number | null;
};
