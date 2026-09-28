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
    {to: "/users", labelKey: "nav.users", end: true, can: "users.list"},
    {to: "/roles", labelKey: "nav.roles", end: true, can: "roles.list"},
    {to: "/permissions", labelKey: "nav.permissions", end: true, can: "permissions.list"},
];
