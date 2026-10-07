import {MessageSquare, Search, SquarePen} from "lucide-react";

import {Button} from "@/components/ui/button";
import {Input} from "@/components/ui/input";
import {useDebouncedSearch} from "@/shared/lib/hooks/useDebouncedSearch";
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
    /** The search in effect; `onSearch` gets the text once typing pauses. */
    query: string;
    onSearch: (query: string) => void;
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
    query,
    onSearch,
}: ChatHistoryProps) {
    const {t} = useI18n();
    const [search, setSearch] = useDebouncedSearch(query, onSearch);
    return (
        <div className="flex h-full min-h-0 flex-col">
            <div className="flex shrink-0 flex-col gap-1.5 p-2">
                <Button type="button" variant="ghost" className="w-full justify-start" disabled={disabled} onClick={onNew}>
                    <SquarePen aria-hidden />
                    {t("chat.newChat")}
                </Button>
                <div className="relative">
                    <Search
                        className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
                        aria-hidden
                    />
                    <Input
                        type="search"
                        value={search}
                        placeholder={t("chat.searchHistory")}
                        aria-label={t("chat.searchHistory")}
                        autoComplete="off"
                        maxLength={100}
                        className="pl-8"
                        onChange={(event) => setSearch(event.target.value)}
                    />
                </div>
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
                    {query ? t("chat.historyNoMatch") : t("chat.historyEmpty")}
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
                                        <li key={conversation.id}>
                                            <button
                                                type="button"
                                                disabled={disabled}
                                                aria-current={active ? "true" : undefined}
                                                title={conversation.title}
                                                onClick={() => onOpen(conversation.id)}
                                                className={cn(
                                                    "block w-full cursor-pointer truncate rounded-lg px-2.5 py-2 text-left text-sm outline-none transition-colors hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed",
                                                    active && "bg-muted font-medium",
                                                )}
                                            >
                                                {conversation.title}
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
