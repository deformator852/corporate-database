import {MessageSquare, SquarePen, Trash2} from "lucide-react";

import {Button} from "@/components/ui/button";
import {cn} from "cn";
import {useI18n} from "@/shared/i18n/I18nProvider";
import type {MessageKey} from "@/shared/i18n/messages";
import type {ChatConversationItem} from "@pages/home/model/chat";

type ChatHistoryProps = {
    conversations: ChatConversationItem[] | null;
    error: string | null;
    activeId: number | null;
    disabled: boolean;
    onNew: () => void;
    onOpen: (id: number) => void;
    onDelete: (id: number) => void;
};

const DAY_MS = 24 * 60 * 60 * 1000;

/** Age groups of the list, as ChatGPT shows them: by days since local midnight. */
const GROUPS: [MessageKey, number][] = [
    ["chat.historyToday", 0],
    ["chat.historyYesterday", 1],
    ["chat.historyWeek", 7],
    ["chat.historyMonth", 30],
    ["chat.historyOlder", Number.POSITIVE_INFINITY],
];

function groupByAge(conversations: ChatConversationItem[], now = new Date()) {
    const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const groups = GROUPS.map(([label]) => ({label, items: [] as ChatConversationItem[]}));
    for (const conversation of conversations) {
        const days = Math.max(0, Math.ceil((midnight - new Date(conversation.updated_at).getTime()) / DAY_MS));
        groups[GROUPS.findIndex(([, maxDays]) => days <= maxDays)].items.push(conversation);
    }
    return groups.filter((group) => group.items.length > 0);
}

/** Saved chats of the signed-in user, newest first, grouped by age. */
export function ChatHistory({
    conversations,
    error,
    activeId,
    disabled,
    onNew,
    onOpen,
    onDelete,
}: ChatHistoryProps) {
    const {t} = useI18n();
    return (
        <div className="flex h-full min-h-0 flex-col">
            <div className="shrink-0 p-2">
                <Button type="button" variant="ghost" className="w-full justify-start" disabled={disabled} onClick={onNew}>
                    <SquarePen aria-hidden />
                    {t("chat.newChat")}
                </Button>
            </div>
            {error ? (
                <p role="alert" className="px-3 py-4 text-sm text-destructive">
                    {error}
                </p>
            ) : conversations == null ? (
                <p className="px-3 py-4 text-sm text-muted-foreground">{t("common.loading")}</p>
            ) : conversations.length === 0 ? (
                <div className="flex flex-col items-center gap-2 px-4 py-10 text-center text-sm text-muted-foreground">
                    <MessageSquare className="size-5" aria-hidden />
                    {t("chat.historyEmpty")}
                </div>
            ) : (
                <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 pb-2">
                    {groupByAge(conversations).map((group) => (
                        <section key={group.label} aria-label={t(group.label)} className="mt-3 first:mt-1">
                            <h2 className="px-2.5 pb-1 text-xs font-medium text-muted-foreground">{t(group.label)}</h2>
                            <ul className="list-none ps-0">
                                {group.items.map((conversation) => {
                                    const active = conversation.id === activeId;
                                    return (
                                        <li key={conversation.id} className="group relative">
                                            <button
                                                type="button"
                                                disabled={disabled}
                                                aria-current={active ? "true" : undefined}
                                                title={conversation.title}
                                                onClick={() => onOpen(conversation.id)}
                                                className={cn(
                                                    "block w-full cursor-pointer truncate rounded-lg px-2.5 py-2 pr-9 text-left text-sm outline-none transition-colors hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed",
                                                    active && "bg-muted font-medium",
                                                )}
                                            >
                                                {conversation.title}
                                            </button>
                                            <button
                                                type="button"
                                                disabled={disabled}
                                                aria-label={t("chat.deleteChat")}
                                                title={t("chat.deleteChat")}
                                                onClick={() => onDelete(conversation.id)}
                                                className="absolute top-1/2 right-1.5 flex size-7 -translate-y-1/2 cursor-pointer items-center justify-center rounded-md text-muted-foreground opacity-0 outline-none transition-opacity group-hover:opacity-100 hover:bg-background hover:text-destructive focus-visible:opacity-100 focus-visible:ring-3 focus-visible:ring-ring/50 [@media(hover:none)]:opacity-100"
                                            >
                                                <Trash2 className="size-3.5" aria-hidden />
                                            </button>
                                        </li>
                                    );
                                })}
                            </ul>
                        </section>
                    ))}
                </div>
            )}
        </div>
    );
}
