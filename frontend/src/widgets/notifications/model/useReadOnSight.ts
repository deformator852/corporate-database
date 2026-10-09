import {useEffect, useEffectEvent} from "react";

/** While `open`, calls `onSeen(id)` once for each unread item of `list`
 * (`data-unread="true"`, `data-notification-id`) that scrolls into view.
 * `unreadKey` changes when the unread items do, to watch the new ones. */
export function useReadOnSight(
    list: HTMLElement | null,
    open: boolean,
    unreadKey: string,
    onSeen: (id: number) => void,
) {
    const seenNow = useEffectEvent(onSeen);

    useEffect(() => {
        if (!open || list == null || unreadKey.length === 0) {
            return;
        }
        const seen = new Set<number>();
        const observer = new IntersectionObserver(
            (entries) => {
                for (const entry of entries) {
                    const id = Number(entry.target.getAttribute("data-notification-id"));
                    if (entry.isIntersecting && Number.isInteger(id) && !seen.has(id)) {
                        seen.add(id);
                        seenNow(id);
                    }
                }
            },
            {root: list, threshold: 0.6},
        );
        for (const node of list.querySelectorAll("[data-unread='true']")) {
            observer.observe(node);
        }
        return () => observer.disconnect();
    }, [open, list, unreadKey]);
}
