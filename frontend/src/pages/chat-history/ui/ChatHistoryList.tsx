import {Eraser, X} from "lucide-react";
import {useState} from "react";
import {Link, useLocation} from "react-router";

import {Button} from "@/components/ui/button";
import {TableCell, TableRow} from "@/components/ui/table";
import type {ChatHistoryLinkState} from "@/entities/chat/model";
import type {UserDetailLinkState} from "@/entities/user/model";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {localeIntlTag} from "@/shared/i18n/messages";
import {can} from "@/shared/lib/api/me";
import {refreshAfterDelete, usePageParam} from "@/shared/lib/hooks/usePageParam";
import {useRequest} from "@/shared/lib/hooks/useRequest";
import {useUrlParams} from "@/shared/lib/hooks/useUrlParams";
import {formatDateTime} from "@/shared/lib/time";
import {ListPagination} from "@/shared/ui/ListPagination";
import {DataTable} from "@/shared/ui/DataTable";
import {PageHeader} from "@/shared/ui/PageHeader";
import {DeleteButton} from "@/shared/ui/DeleteButton";
import {StatusCard} from "@/shared/ui/StatusCard";
import {ChatPurgeDialog} from "@/widgets/chat-purge/ui/ChatPurgeDialog";
import {getReviewedChats} from "@pages/chat-history/api/chatHistory";
import {ChatDeleteDialog} from "@pages/chat-history/ui/ChatDeleteDialog";

/** Every user's saved chats (`?user=` narrows to one), read-only, with deleting one or clearing many. */
export function ChatHistoryList() {
    const {t, locale} = useI18n();
    const location = useLocation();
    const [params, updateParams] = useUrlParams();
    const [page, goToPage] = usePageParam();
    const userParam = Number(params.get("user"));
    const userId = Number.isInteger(userParam) && userParam > 0 ? userParam : null;
    const {status, data, error, reload} = useRequest(
        `${page}:${userId}`,
        () => getReviewedChats(page, userId),
        t("chatHistory.loadError"),
    );
    const [purging, setPurging] = useState(false);
    const [purged, setPurged] = useState<string | null>(null);
    const [deleting, setDeleting] = useState<{id: number; userName: string} | null>(null);
    const canDelete = can("chat.purge");
    const items = data?.items ?? [];
    const owner = items[0]?.user;
    const ownerName =
        owner?.name || owner?.email || (location.state as ChatHistoryLinkState | null)?.userName || `#${userId}`;
    const tag = localeIntlTag(locale);
    // Pages opened from here come back to it.
    const linkState: UserDetailLinkState = {from: location.pathname + location.search};

    return (
        <div className="stack stack--lg w-full">
            <PageHeader
                title={t("chatHistory.title")}
                subtitle={t("chatHistory.subtitle")}
                action={
                    can("chat.purge") ? (
                        <Button type="button" variant="destructive" onClick={() => setPurging(true)}>
                            <Eraser aria-hidden />
                            {t("chatPurge.open")}
                        </Button>
                    ) : null
                }
            />

            {userId != null ? (
                <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="text-base-content/70">{t("chatHistory.userFilter")}</span>
                    <span className="d-badge h-auto gap-0.5 bg-base-200 py-0.5 ps-2.5 pe-0.5">
                        {ownerName}
                        <Button
                            type="button"
                            variant="ghost"
                            size="icon-xs"
                            className="rounded-full"
                            aria-label={t("chatHistory.allUsers")}
                            onClick={() => updateParams({user: "", page: "1"})}
                        >
                            <X aria-hidden />
                        </Button>
                    </span>
                </div>
            ) : null}

            {purged ? (
                <p role="status" className="text-sm text-base-content/70">
                    {purged}
                </p>
            ) : null}

            {status === "error" ? (
                <StatusCard title={t("chatHistory.loadErrorTitle")} detail={error} onRetry={reload} />
            ) : status === "loading" ? (
                <p className="text-sm text-base-content/70">{t("chatHistory.loading")}</p>
            ) : items.length === 0 ? (
                <StatusCard title={t("chatHistory.empty")} />
            ) : (
                <div className="stack">
                    <DataTable
                        aria-label={t("chatHistory.title")}
                        columns={[
                            {label: t("chatHistory.chat"), className: "px-4"},
                            {label: t("chatHistory.user")},
                            {label: t("chatHistory.messages"), className: "text-right"},
                            {label: t("chatHistory.lastActivity"), className: "px-4"},
                            canDelete && {label: <span className="sr-only">{t("common.actions")}</span>, className: "px-4"},
                        ]}
                    >
                        {items.map((chat) => (
                            <TableRow key={chat.id}>
                                <TableCell className="max-w-80 px-4 font-medium">
                                    <Link
                                        to={`/chat-history/${chat.id}`}
                                        state={linkState}
                                        title={chat.title}
                                        className="block truncate underline-offset-4 hover:underline"
                                    >
                                        {chat.title}
                                    </Link>
                                </TableCell>
                                <TableCell>
                                    <button
                                        type="button"
                                        className="d-link d-link-hover text-left"
                                        title={t("chatHistory.onlyUser", {name: chat.user.name})}
                                        onClick={() => updateParams({user: String(chat.user.id), page: "1"})}
                                    >
                                        {chat.user.name || chat.user.email}
                                    </button>
                                </TableCell>
                                <TableCell className="text-right tabular-nums">{chat.message_count}</TableCell>
                                <TableCell className="px-4 text-base-content/70 tabular-nums">
                                    {formatDateTime(chat.updated_at, tag)}
                                </TableCell>
                                {canDelete ? (
                                    <TableCell className="px-4 text-right">
                                        <DeleteButton
                                            aria-label={t("chatHistory.delete.aria", {title: chat.title})}
                                            onClick={() => setDeleting({id: chat.id, userName: chat.user.name || chat.user.email})}
                                        />
                                    </TableCell>
                                ) : null}
                            </TableRow>
                        ))}
                    </DataTable>
                    {data && data.pages > 1 ? (
                        <ListPagination
                            page={page}
                            pages={data.pages}
                            perPage={data.per_page}
                            total={data.total}
                            shown={items.length}
                            onPageChange={goToPage}
                        />
                    ) : null}
                </div>
            )}

            <ChatPurgeDialog
                open={purging}
                onOpenChange={setPurging}
                user={userId != null ? {id: userId, name: ownerName} : undefined}
                onPurged={(deleted) => {
                    setPurged(t("chatPurge.done", {count: deleted}));
                    if (page > 1) {
                        goToPage(1);
                    } else {
                        reload();
                    }
                }}
            />
            <ChatDeleteDialog
                chat={deleting}
                onClose={() => setDeleting(null)}
                onDeleted={() => refreshAfterDelete(page, items.length, goToPage, reload)}
            />
        </div>
    );
}
