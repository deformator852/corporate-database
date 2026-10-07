import {useEffect, useEffectEvent, useState} from "react";

const DEBOUNCE_MS = 300;

/** A search box: the text as typed, and `commit` with it once typing pauses.
 * `committed` is the search in effect (from the URL), which the box follows
 * when it changes elsewhere (back button, a "clear filters" link). */
export function useDebouncedSearch(committed: string, commit: (query: string) => void): [string, (query: string) => void] {
    const [draft, setDraft] = useState(committed);
    const [lastCommitted, setLastCommitted] = useState(committed);
    if (committed !== lastCommitted) {
        setLastCommitted(committed);
        setDraft(committed);
    }
    const onPause = useEffectEvent(commit);

    useEffect(() => {
        const next = draft.trim();
        if (next === committed) {
            return;
        }
        const timer = window.setTimeout(() => onPause(next), DEBOUNCE_MS);
        return () => window.clearTimeout(timer);
    }, [draft, committed]);

    return [draft, setDraft];
}
