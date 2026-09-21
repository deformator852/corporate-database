import {useCallback, useEffect, useRef} from "react";

import {markNotificationsRead} from "@/widgets/notifications/api/notifications";
import {NOTIFICATION_READ_BATCH_MS} from "@/widgets/notifications/model/notifications";

export function useNotificationReadBatch() {
    const pending = useRef(new Set<number>());
    const timer = useRef<number>(undefined);

    const flush = useCallback((keepalive = false) => {
        if (timer.current != null) {
            window.clearTimeout(timer.current);
            timer.current = undefined;
        }
        const ids = [...pending.current];
        pending.current.clear();
        if (ids.length === 0) {
            return;
        }
        void markNotificationsRead(ids, {keepalive}).catch(() => {
            for (const id of ids) {
                pending.current.add(id);
            }
        });
    }, []);

    const queue = useCallback(
        (id: number) => {
            pending.current.add(id);
            if (timer.current != null) {
                return;
            }
            timer.current = window.setTimeout(() => {
                timer.current = undefined;
                flush();
            }, NOTIFICATION_READ_BATCH_MS);
        },
        [flush],
    );

    useEffect(() => {
        function onPageHide() {
            flush(true);
        }
        function onVisibility() {
            if (document.visibilityState === "hidden") {
                flush(true);
            }
        }
        document.addEventListener("visibilitychange", onVisibility);
        window.addEventListener("pagehide", onPageHide);
        return () => {
            document.removeEventListener("visibilitychange", onVisibility);
            window.removeEventListener("pagehide", onPageHide);
            flush(true);
        };
    }, [flush]);

    return {queue, flush};
}
