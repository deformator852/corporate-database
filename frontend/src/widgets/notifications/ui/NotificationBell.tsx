import {Bell, BellOff, CircleAlert, CircleCheck, X} from "lucide-react";
import {useState} from "react";

import {Button} from "@/components/ui/button";
import {Popover, PopoverContent, PopoverTrigger} from "@/components/ui/popover";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {localeIntlTag} from "@/shared/i18n/messages";
import {cn} from "cn";
import {
    formatNotificationTime,
    formatRelativeTime,
    isFailure,
    notificationTypeKey,
    type NotificationItem,
} from "@/widgets/notifications/model/notifications";
import {useNotificationFeed} from "@/widgets/notifications/model/useNotificationFeed";
import {useNotificationReadBatch} from "@/widgets/notifications/model/useNotificationReadBatch";
import {useReadOnSight} from "@/widgets/notifications/model/useReadOnSight";

export function NotificationBell() {
    const {t} = useI18n();
    const [open, setOpen] = useState(false);
    // State, not a ref: the list mounts after the popover opens, and the
    // read observer must attach once it exists.
    const [list, setList] = useState<HTMLUListElement | null>(null);
    // Unread when the panel opened: stay highlighted as "new" until it closes,
    // even though they are marked read as soon as they are seen.
    const [fresh, setFresh] = useState<ReadonlySet<number>>(new Set());
    const {queue, flush} = useNotificationReadBatch();
    const feed = useNotificationFeed();
    const {data} = feed;
    const unreadCount = data?.unread_count ?? 0;

    const unreadKey =
        data?.items
            .filter((item) => !item.read)
            .map((item) => item.id)
            .join(",") ?? "";
    useReadOnSight(list, open, unreadKey, (id) => {
        queue(id);
        setFresh((current) => new Set(current).add(id));
        feed.markRead(id);
    });

    function handleScroll() {
        if (list != null && list.scrollHeight - list.scrollTop - list.clientHeight <= 80) {
            void feed.loadMore();
        }
    }

    let body;
    if (feed.error) {
        body = (
            <div className="flex flex-col items-start gap-3 px-4 py-5">
                <p className="text-sm text-muted-foreground">{feed.error}</p>
                <Button type="button" variant="outline" size="sm" onClick={feed.retry}>
                    {t("common.tryAgain")}
                </Button>
            </div>
        );
    } else if (data && data.items.length > 0) {
        body = (
            <ul
                ref={setList}
                className="max-h-[min(26rem,70vh)] list-none overflow-y-auto overscroll-contain p-0"
                onScroll={handleScroll}
            >
                {data.items.map((item) => (
                    <NotificationRow
                        key={item.id}
                        item={item}
                        isNew={!item.read || fresh.has(item.id)}
                        onDismiss={() => void feed.dismiss(item.id)}
                    />
                ))}
            </ul>
        );
    } else if (feed.loading) {
        body = <p className="px-4 py-8 text-center text-sm text-muted-foreground">{t("notifications.loading")}</p>;
    } else {
        body = (
            <div className="flex flex-col items-center gap-2 px-6 py-10 text-center">
                <span className="flex size-11 items-center justify-center rounded-full bg-muted text-muted-foreground">
                    <BellOff className="size-5" aria-hidden />
                </span>
                <p className="font-medium">{t("notifications.empty")}</p>
                <p className="text-sm text-muted-foreground">{t("notifications.emptyHint")}</p>
            </div>
        );
    }

    return (
        <Popover
            open={open}
            onOpenChange={(next) => {
                setOpen(next);
                if (!next) {
                    flush(true);
                    setFresh(new Set());
                }
            }}
        >
            <PopoverTrigger
                render={
                    <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="relative"
                        aria-label={
                            unreadCount > 0 ? t("notifications.unread", {count: unreadCount}) : t("notifications.label")
                        }
                    />
                }
            >
                <Bell />
                {unreadCount > 0 ? (
                    <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] leading-none font-semibold text-destructive-foreground ring-2 ring-background">
                        {unreadCount > 9 ? "9+" : unreadCount}
                    </span>
                ) : null}
            </PopoverTrigger>
            <PopoverContent
                align="end"
                className="w-96 max-w-[calc(100vw-1.5rem)] overflow-hidden p-0"
                aria-label={t("notifications.label")}
            >
                <div className="flex items-center justify-between gap-2 border-b px-4 py-3">
                    <div className="flex items-center gap-2">
                        <p className="font-semibold">{t("notifications.label")}</p>
                        {unreadCount > 0 ? (
                            <span className="rounded-full bg-primary px-1.5 py-0.5 text-[11px] leading-none font-semibold text-primary-foreground tabular-nums">
                                {unreadCount}
                            </span>
                        ) : null}
                    </div>
                    <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="text-muted-foreground"
                        disabled={!data || data.total === 0}
                        onClick={() => void feed.clear()}
                    >
                        {t("notifications.clearAll")}
                    </Button>
                </div>
                {body}
            </PopoverContent>
        </Popover>
    );
}

function NotificationRow({item, isNew, onDismiss}: {item: NotificationItem; isNew: boolean; onDismiss: () => void}) {
    const {t, locale} = useI18n();
    const failed = isFailure(item.type);
    const Icon = failed ? CircleAlert : CircleCheck;

    return (
        <li
            data-notification-id={item.id}
            data-unread={item.read ? undefined : "true"}
            className={cn(
                "group relative flex gap-3 border-b px-4 py-3 transition-colors last:border-b-0 hover:bg-muted/60",
                isNew && "bg-primary/5",
            )}
        >
            <span
                className={cn(
                    "mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full",
                    failed ? "bg-destructive/10 text-destructive" : "bg-success/10 text-success",
                )}
                aria-hidden
            >
                <Icon className="size-4" />
            </span>
            <div className="min-w-0 flex-1 pr-6">
                <p className="flex items-center gap-1.5 font-medium">
                    {isNew ? <span className="sr-only">{t("notifications.new")}</span> : null}
                    <span className="truncate">{t(notificationTypeKey(item.type))}</span>
                </p>
                <p className="mt-0.5 text-sm break-words text-muted-foreground">{item.message}</p>
                <time
                    dateTime={item.created_at}
                    title={formatNotificationTime(item.created_at, localeIntlTag(locale))}
                    className="mt-1 block text-xs text-muted-foreground"
                >
                    {formatRelativeTime(item.created_at, localeIntlTag(locale))}
                </time>
            </div>
            <button
                type="button"
                aria-label={t("notifications.dismiss")}
                title={t("notifications.dismiss")}
                onClick={onDismiss}
                className="absolute top-2.5 right-2.5 flex size-7 cursor-pointer items-center justify-center rounded-md text-muted-foreground opacity-0 transition-opacity outline-none group-hover:opacity-100 hover:bg-muted hover:text-foreground focus-visible:opacity-100 focus-visible:ring-3 focus-visible:ring-ring/50 [@media(hover:none)]:opacity-100"
            >
                <X className="size-4" aria-hidden />
            </button>
        </li>
    );
}
