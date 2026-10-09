import {
    Activity,
    Bug,
    FileText,
    House,
    KeyRound,
    MessageSquareWarning,
    MessagesSquare,
    ScrollText,
    ShieldCheck,
    Users,
    type LucideIcon,
} from "lucide-react";

import type {CustomMessageKey, MessageKey} from "@/shared/i18n/messages";

export type NavItem = {
    to: string;
    labelKey: MessageKey | CustomMessageKey;
    end?: boolean;
    can?: string;
    icon?: LucideIcon;
};

export const CORE_NAV: NavItem[] = [
    {to: "/", labelKey: "nav.home", end: true, icon: House},
    {to: "/documents", labelKey: "nav.documents", end: true, can: "documents.list", icon: FileText},
    // Not `end`: stays active on the user page /users/:id.
    {to: "/users", labelKey: "nav.users", can: "users.list", icon: Users},
    {to: "/roles", labelKey: "nav.roles", end: true, can: "roles.list", icon: ShieldCheck},
    {to: "/permissions", labelKey: "nav.permissions", end: true, can: "permissions.list", icon: KeyRound},
    // Not `end`: stays active on a chat, /chat-history/:id.
    {to: "/chat-history", labelKey: "nav.chatHistory", can: "chat.history", icon: MessagesSquare},
    {to: "/feedback", labelKey: "nav.feedback", end: true, can: "chat.feedback", icon: MessageSquareWarning},
    {to: "/audit", labelKey: "nav.audit", end: true, can: "audit.list", icon: ScrollText},
    {to: "/system", labelKey: "nav.system", end: true, can: "system.view", icon: Activity},
    {to: "/errors", labelKey: "nav.errorLog", end: true, can: "system.errors", icon: Bug},
];
