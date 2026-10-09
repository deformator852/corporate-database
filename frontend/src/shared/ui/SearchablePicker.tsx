import {useEffect, useEffectEvent, useRef, useState} from "react";

import {Button} from "@/components/ui/button";
import {Checkbox} from "@/components/ui/checkbox";
import {Input} from "@/components/ui/input";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {useDebouncedSearch} from "@/shared/lib/hooks/useDebouncedSearch";

const PAGE_SIZE = 10;
// Load the next page this close to the end of the list.
const LOAD_MORE_MARGIN_PX = 48;

type PickerItem = {key: string; name: string};

type PickerPage<T extends PickerItem> = {items: T[]; page: number; pages: number};

/** Texts of one picker; the shared ones (selected count, loading more, try
 * again) come from `common.*`. */
export type SearchablePickerLabels = {
    search: string;
    loading: string;
    loadError: string;
    empty: string;
    emptySearch: string;
};

type SearchablePickerProps<T extends PickerItem> = {
    value: string[];
    onChange: (keys: string[]) => void;
    /** Loads only while true (the dialog is open). */
    enabled: boolean;
    loadPage: (page: number, perPage: number, query: string) => Promise<PickerPage<T>>;
    labels: SearchablePickerLabels;
    /** Prefix of the checkbox ids, unique on the page. */
    idPrefix: string;
    /** Always checked and not changeable, with `lockedReason` as the hint. */
    lockedKeys?: string[];
    lockedReason?: string;
};

type PickerState<T> = {
    query: string;
    page: number;
    pages: number;
    items: T[];
    status: "ready" | "error";
    message?: string;
};

/** A searchable checkbox list that loads more as it is scrolled. */
export function SearchablePicker<T extends PickerItem>({
    value,
    onChange,
    enabled,
    loadPage,
    labels,
    idPrefix,
    lockedKeys = [],
    lockedReason,
}: SearchablePickerProps<T>) {
    const {t} = useI18n();
    const [query, setQuery] = useState("");
    const [search, setSearch] = useDebouncedSearch(query, setQuery);
    const {loaded, page, items, canLoadMore, loadNextPage, error, retry} = usePickerPages(
        loadPage,
        query,
        enabled,
        labels.loadError,
    );
    const scrollerRef = useRef<HTMLDivElement>(null);
    const locked = new Set(lockedKeys);

    // Near the end of the list, or when the loaded items do not fill it
    // (nothing to scroll yet).
    const loadIfAtEnd = () => {
        const scroller = scrollerRef.current;
        if (canLoadMore && scroller != null) {
            const left = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
            if (left <= LOAD_MORE_MARGIN_PX) {
                loadNextPage();
            }
        }
    };
    const loadIfAtEndAfterRender = useEffectEvent(loadIfAtEnd);
    useEffect(() => {
        loadIfAtEndAfterRender();
    }, [canLoadMore, page]);

    const toggle = (key: string, checked: boolean) => {
        const selected = new Set(value);
        if (checked) {
            selected.add(key);
        } else {
            selected.delete(key);
        }
        onChange([...selected]);
    };

    let list;
    if (items.length > 0) {
        list = (
            <div
                ref={scrollerRef}
                className="max-h-40 overflow-y-auto overscroll-contain rounded-lg border border-input"
                onScroll={loadIfAtEnd}
            >
                {items.map((item) => (
                    <PickerOption
                        key={item.key}
                        id={`${idPrefix}-${item.key}`}
                        name={item.name}
                        checked={value.includes(item.key)}
                        lockedReason={locked.has(item.key) ? lockedReason ?? "" : null}
                        onChange={(checked) => toggle(item.key, checked)}
                    />
                ))}
                {canLoadMore ? (
                    <div className="px-3 py-2 text-sm text-muted-foreground">{t("common.loadingMore")}</div>
                ) : null}
            </div>
        );
    } else if (!error) {
        list = (
            <p className="text-sm text-muted-foreground">
                {!loaded ? labels.loading : query ? labels.emptySearch : labels.empty}
            </p>
        );
    }

    return (
        <div className="flex min-h-0 flex-col gap-2">
            <Input
                type="search"
                value={search}
                placeholder={labels.search}
                aria-label={labels.search}
                autoComplete="off"
                onKeyDown={(event) => {
                    if (event.key === "Enter") {
                        event.preventDefault();
                    }
                }}
                onChange={(event) => setSearch(event.target.value)}
            />
            {value.length > 0 ? (
                <p className="text-sm text-muted-foreground">{t("common.selectedCount", {count: value.length})}</p>
            ) : null}
            {list}
            {error ? <PickerError message={error} onRetry={retry} /> : null}
        </div>
    );
}

/** A checkbox of the list; a locked one stays checked, with the reason as
 * its hint. */
function PickerOption({
    id,
    name,
    checked,
    lockedReason,
    onChange,
}: {
    id: string;
    name: string;
    checked: boolean;
    lockedReason: string | null;
    onChange: (checked: boolean) => void;
}) {
    const isLocked = lockedReason !== null;
    return (
        <label
            htmlFor={id}
            className={`flex items-center gap-2 border-b border-input px-3 py-2 text-sm last:border-b-0 ${
                isLocked ? "cursor-not-allowed opacity-70" : "cursor-pointer"
            }`}
        >
            <Checkbox
                id={id}
                disabled={isLocked}
                title={isLocked ? lockedReason : undefined}
                checked={isLocked || checked}
                onCheckedChange={(next) => {
                    if (!isLocked) {
                        onChange(Boolean(next));
                    }
                }}
            />
            {name}
        </label>
    );
}

/** The pages of `query` loaded so far, while `enabled`: the first page
 * whenever the query changes, the next one on `loadNextPage`. A failure
 * keeps what was loaded; `retry` tries the failed page again. */
function usePickerPages<T extends PickerItem>(
    loadPage: (page: number, perPage: number, query: string) => Promise<PickerPage<T>>,
    query: string,
    enabled: boolean,
    loadError: string,
) {
    const [retryKey, setRetryKey] = useState(0);
    const [state, setState] = useState<PickerState<T> | null>(null);
    const loadingMore = useRef(false);
    const failed = (reason: unknown) => getApiErrorMessage(reason, loadError);

    const loadFirstPage = useEffectEvent((isCurrent: () => boolean) => {
        void loadPage(1, PAGE_SIZE, query)
            .then((page) => {
                if (isCurrent()) {
                    setState({query, page: page.page, pages: page.pages, items: page.items, status: "ready"});
                }
            })
            .catch((reason: unknown) => {
                if (isCurrent()) {
                    setState({query, page: 1, pages: 0, items: [], status: "error", message: failed(reason)});
                }
            });
    });

    useEffect(() => {
        if (!enabled) {
            return;
        }
        let current = true;
        loadFirstPage(() => current);
        return () => {
            current = false;
        };
    }, [enabled, query, retryKey]);

    // A page of an older query is not shown.
    const shown = state?.query === query ? state : null;
    const items = shown?.items ?? [];

    const loadNextPage = () => {
        if (loadingMore.current || shown == null) {
            return;
        }
        loadingMore.current = true;
        const next = shown.page + 1;
        void loadPage(next, PAGE_SIZE, query)
            .then((page) =>
                setState((current) =>
                    current?.query === query && current.page === next - 1
                        ? {...current, page: page.page, pages: page.pages, items: merged(current.items, page.items)}
                        : current,
                ),
            )
            .catch((reason: unknown) =>
                setState((current) =>
                    current?.query === query ? {...current, status: "error", message: failed(reason)} : current,
                ),
            )
            .finally(() => {
                loadingMore.current = false;
            });
    };

    const retry = () => {
        if (items.length > 0) {
            setState((current) => (current == null ? current : {...current, status: "ready", message: undefined}));
            loadNextPage();
            return;
        }
        setState(null);
        setRetryKey((key) => key + 1);
    };

    return {
        loaded: shown != null,
        page: shown?.page,
        items,
        canLoadMore: enabled && shown?.status === "ready" && shown.page < shown.pages,
        loadNextPage,
        error: shown?.status === "error" ? (shown.message ?? loadError) : null,
        retry,
    };
}

function merged<T extends PickerItem>(current: T[], incoming: T[]): T[] {
    const seen = new Set(current.map((item) => item.key));
    return [...current, ...incoming.filter((item) => !seen.has(item.key))];
}

function PickerError({message, onRetry}: {message: string; onRetry: () => void}) {
    const {t} = useI18n();
    return (
        <div className="flex flex-col items-start gap-2">
            <p className="text-sm text-destructive">{message}</p>
            <Button type="button" variant="outline" size="sm" onClick={onRetry}>
                {t("common.tryAgain")}
            </Button>
        </div>
    );
}
