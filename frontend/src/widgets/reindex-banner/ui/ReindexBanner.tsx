import {RefreshCw} from "lucide-react";
import {useEffect, useState} from "react";

import {useI18n} from "@/shared/i18n/I18nProvider";
import {getReindexProgress, type ReindexProgress} from "@/widgets/reindex-banner/api/reindex";

// A switch starts rarely: checked now and then; while it runs, more often.
const IDLE_MS = 60_000;
const ACTIVE_MS = 15_000;

/** A strip over every page while documents are embedded again for a new
 * embedding model: until then answers may miss some documents. */
export function ReindexBanner() {
    const {t} = useI18n();
    const [progress, setProgress] = useState<ReindexProgress | null>(null);

    useEffect(() => {
        let timer: number | undefined;
        let stopped = false;
        const check = (active: boolean) => {
            timer = window.setTimeout(poll, active ? ACTIVE_MS : IDLE_MS);
        };
        const poll = () => {
            void getReindexProgress()
                .then((next) => {
                    if (!stopped) {
                        setProgress(next);
                        check(next.active);
                    }
                })
                // Not worth an error of its own: the next check tries again.
                .catch(() => !stopped && check(false));
        };
        poll();
        return () => {
            stopped = true;
            window.clearTimeout(timer);
        };
    }, []);

    if (!progress?.active) {
        return null;
    }
    return (
        <div
            role="status"
            // Up against the header: the main area's top padding goes below it.
            className="-mt-(--section-gap) mb-(--section-gap) flex items-center gap-2 border-b border-amber-300/60 bg-amber-50 px-4 py-2 text-sm text-amber-950 dark:border-amber-500/30 dark:bg-amber-950/40 dark:text-amber-100"
        >
            <RefreshCw className="size-4 shrink-0 animate-spin [animation-duration:3s] motion-reduce:animate-none" aria-hidden />
            <p>{t("reindex.banner", {percent: progress.percent})}</p>
        </div>
    );
}
