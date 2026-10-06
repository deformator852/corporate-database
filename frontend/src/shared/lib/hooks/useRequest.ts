import {useEffect, useEffectEvent, useState} from "react";

import {getApiErrorMessage} from "@/shared/lib/api/errors";

type Settled<T> = {key: string; status: "ready"; data: T} | {key: string; status: "error"; message: string};

export type RequestStatus = "loading" | "ready" | "error";

/**
 * Data loaded by `load`, again whenever `key` changes or `reload` is called.
 * A late answer to an older key is dropped. `key` null: nothing is loaded.
 */
export function useRequest<T>(key: string | null, load: () => Promise<T>, errorFallback: string) {
    const [reloads, setReloads] = useState(0);
    const requestKey = key == null ? null : `${key}:${reloads}`;
    const [settled, setSettled] = useState<Settled<T> | null>(null);

    const start = useEffectEvent((requested: string, isCurrent: () => boolean) => {
        void load()
            .then((data) => {
                if (isCurrent()) {
                    setSettled({key: requested, status: "ready", data});
                }
            })
            .catch((reason: unknown) => {
                if (isCurrent()) {
                    setSettled({key: requested, status: "error", message: getApiErrorMessage(reason, errorFallback)});
                }
            });
    });

    useEffect(() => {
        if (requestKey == null) {
            return;
        }
        let current = true;
        start(requestKey, () => current);
        return () => {
            current = false;
        };
    }, [requestKey]);

    const shown = settled?.key === requestKey ? settled : null;
    return {
        status: (shown?.status ?? "loading") as RequestStatus,
        data: shown?.status === "ready" ? shown.data : null,
        error: shown?.status === "error" ? shown.message : null,
        reload: () => setReloads((count) => count + 1),
        /** Changes the loaded data in place, e.g. from a live event. */
        update: (change: (data: T) => T) =>
            setSettled((current) => (current?.status === "ready" ? {...current, data: change(current.data)} : current)),
    };
}
