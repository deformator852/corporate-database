import {MessageSquare, Plus, Trash2} from "lucide-react";

import {Button} from "@/components/ui/button";
import {cn} from "cn";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {localeIntlTag} from "@/shared/i18n/messages";
import {formatRelativeTime} from "@/shared/lib/time";
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

/** Saved chats of the signed-in user, newest first. */
export function ChatHistory({
    conversations,
    error,
    activeId,
    disabled,
    onNew,
    onOpen,
    onDelete,
}: ChatHistoryProps) {
    const {t, locale} = useI18n();
    return (
        <div className="flex h-full min-h-0 flex-col">
            <div className="flex shrink-0 items-center justify-between gap-2 border-b px-3 py-2.5">
                <p className="text-sm font-medium">{t("chat.history")}</p>
                <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={onNew}>
                    <Plus aria-hidden />
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
                <ul className="min-h-0 flex-1 list-none overflow-y-auto overscroll-contain p-1.5">
                    {conversations.map((conversation) => {
                        const active = conversation.id === activeId;
                        return (
                            <li key={conversation.id} className="group relative">
                                <button
                                    type="button"
                                    disabled={disabled}
                                    aria-current={active ? "true" : undefined}
                                    onClick={() => onOpen(conversation.id)}
                                    className={cn(
                                        "flex w-full cursor-pointer flex-col items-start gap-0.5 rounded-lg px-2.5 py-2 pr-9 text-left outline-none transition-colors hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed",
                                        active && "bg-muted",
                                    )}
                                >
                                    <span className="line-clamp-2 text-sm font-medium break-words">
                                        {conversation.title}
                                    </span>
                                    <span className="text-xs text-muted-foreground">
                                        {formatRelativeTime(conversation.updated_at, localeIntlTag(locale))}
                                    </span>
                                </button>
                                <button
                                    type="button"
                                    disabled={disabled}
                                    aria-label={t("chat.deleteChat")}
                                    title={t("chat.deleteChat")}
                                    onClick={() => onDelete(conversation.id)}
                                    className="absolute top-2 right-1.5 flex size-7 cursor-pointer items-center justify-center rounded-md text-muted-foreground opacity-0 outline-none transition-opacity group-hover:opacity-100 hover:bg-background hover:text-destructive focus-visible:opacity-100 focus-visible:ring-3 focus-visible:ring-ring/50 [@media(hover:none)]:opacity-100"
                                >
                                    <Trash2 className="size-3.5" aria-hidden />
                                </button>
                            </li>
                        );
                    })}
                </ul>
            )}
        </div>
    );
}
