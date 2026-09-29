import type {CustomMessageKey, MessageKey} from "@/shared/i18n/messages";

export type NavItem = {
    to: string;
    labelKey: MessageKey | CustomMessageKey;
    end?: boolean;
    can?: string;
};

export const CORE_NAV: NavItem[] = [
    {to: "/", labelKey: "nav.home", end: true},
    {to: "/documents", labelKey: "nav.documents", end: true, can: "documents.list"},
    // Not `end`: stays active on the user page /users/:id.
    {to: "/users", labelKey: "nav.users", can: "users.list"},
    {to: "/roles", labelKey: "nav.roles", end: true, can: "roles.list"},
    {to: "/permissions", labelKey: "nav.permissions", end: true, can: "permissions.list"},
    {to: "/audit", labelKey: "nav.audit", end: true, can: "audit.list"},
    {to: "/system", labelKey: "nav.system", end: true, can: "system.view"},
];
