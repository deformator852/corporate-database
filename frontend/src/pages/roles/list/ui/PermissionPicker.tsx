import {useEffect, useRef, useState} from "react";

import {Button} from "@/components/ui/button";
import {Checkbox} from "@/components/ui/checkbox";
import {Input} from "@/components/ui/input";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {getPermissionOptions} from "@pages/roles/list/api/roles";
import type {PermissionRef} from "@pages/roles/list/model/roles";

const SEARCH_DEBOUNCE_MS = 300;

type PermissionPickerProps = {
    value: string[];
    onChange: (keys: string[]) => void;
    enabled: boolean;
};

type PickerState = {
    query: string;
    page: number;
    items: PermissionRef[];
    pages: number;
    status: "loading" | "ready" | "error";
    message?: string;
};

function mergeItems(
    current: PermissionRef[],
    incoming: PermissionRef[],
): PermissionRef[] {
    const seen = new Set(current.map((item) => item.key));
    const next = [...current];
    for (const item of incoming) {
        if (seen.has(item.key)) {
            continue;
        }
        seen.add(item.key);
        next.push(item);
    }
    return next;
}

export function PermissionPicker({
    value,
    onChange,
    enabled,
}: PermissionPickerProps) {
    const [search, setSearch] = useState("");
    const [debouncedQuery, setDebouncedQuery] = useState("");
    const [retryKey, setRetryKey] = useState(0);
    const [state, setState] = useState<PickerState | null>(null);
    const scrollerRef = useRef<HTMLDivElement>(null);
    const sentinelRef = useRef<HTMLDivElement>(null);
    const loadingMoreRef = useRef(false);

    useEffect(() => {
        const timeout = window.setTimeout(() => {
            setDebouncedQuery(search.trim());
        }, SEARCH_DEBOUNCE_MS);
        return () => {
            window.clearTimeout(timeout);
        };
    }, [search]);

    useEffect(() => {
        if (!enabled) {
            return;
        }
        let cancelled = false;
        void getPermissionOptions(1, debouncedQuery)
            .then((page) => {
                if (cancelled) {
                    return;
                }
                setState({
                    query: debouncedQuery,
                    page: page.page,
                    items: page.items,
                    pages: page.pages,
                    status: "ready",
                });
            })
            .catch((reason) => {
                if (cancelled) {
                    return;
                }
                setState({
                    query: debouncedQuery,
                    page: 1,
                    items: [],
                    pages: 0,
                    status: "error",
                    message: getApiErrorMessage(
                        reason,
                        "Could not load permissions.",
                    ),
                });
            });
        return () => {
            cancelled = true;
        };
    }, [enabled, debouncedQuery, retryKey]);

    const canLoadMore =
        enabled &&
        state?.status === "ready" &&
        state.query === debouncedQuery &&
        state.page < state.pages;

    const loadNextPage = () => {
        if (loadingMoreRef.current || state == null) {
            return;
        }
        loadingMoreRef.current = true;
        const nextPage = state.page + 1;
        void getPermissionOptions(nextPage, debouncedQuery)
            .then((page) => {
                setState((current) => {
                    if (
                        current == null ||
                        current.query !== debouncedQuery ||
                        current.page !== nextPage - 1
                    ) {
                        return current;
                    }
                    return {
                        ...current,
                        page: page.page,
                        items: mergeItems(current.items, page.items),
                        pages: page.pages,
                        status: "ready",
                    };
                });
            })
            .catch((reason) => {
                setState((current) => {
                    if (current == null || current.query !== debouncedQuery) {
                        return current;
                    }
                    return {
                        ...current,
                        status: "error",
                        message: getApiErrorMessage(
                            reason,
                            "Could not load permissions.",
                        ),
                    };
                });
            })
            .finally(() => {
                loadingMoreRef.current = false;
            });
    };

    const loadNextPageRef = useRef(loadNextPage);

    useEffect(() => {
        loadNextPageRef.current = loadNextPage;
    });

    useEffect(() => {
        if (!canLoadMore) {
            return;
        }
        const sentinel = sentinelRef.current;
        const root = scrollerRef.current;
        if (sentinel == null || root == null) {
            return;
        }
        const observer = new IntersectionObserver(
            (entries) => {
                if (!entries[0]?.isIntersecting) {
                    return;
                }
                loadNextPageRef.current();
            },
            {root, rootMargin: "48px"},
        );
        observer.observe(sentinel);
        return () => {
            observer.disconnect();
        };
    }, [canLoadMore, debouncedQuery, state?.page]);

    const toggle = (key: string, checked: boolean) => {
        const selected = new Set(value);
        if (checked) {
            selected.add(key);
        } else {
            selected.delete(key);
        }
        onChange([...selected]);
    };

    const items = state?.query === debouncedQuery ? state.items : [];
    const status = state?.query === debouncedQuery ? state.status : "loading";
    const error = status === "error" ? state?.message : null;

    const retry = () => {
        if (items.length === 0) {
            setState((current) =>
                current == null
                    ? current
                    : {...current, status: "loading", message: undefined},
            );
            setRetryKey((key) => key + 1);
            return;
        }
        loadNextPage();
    };

    return (
        <div className="flex min-h-0 flex-col gap-2">
            <Input
                type="search"
                value={search}
                placeholder="Search permissions"
                aria-label="Search permissions"
                autoComplete="off"
                onKeyDown={(event) => {
                    if (event.key === "Enter") {
                        event.preventDefault();
                    }
                }}
                onChange={(event) => {
                    setSearch(event.target.value);
                }}
            />
            {value.length > 0 ? (
                <p className="text-sm text-muted-foreground">
                    {value.length} selected
                </p>
            ) : null}
            {status === "error" && items.length === 0 ? (
                <PickerError
                    message={error ?? "Could not load permissions."}
                    onRetry={retry}
                />
            ) : status === "loading" && items.length === 0 ? (
                <p className="text-sm text-muted-foreground">Loading permissions…</p>
            ) : status === "ready" && items.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                    {debouncedQuery
                        ? "No permissions match this search."
                        : "No permissions are available."}
                </p>
            ) : (
                <div
                    ref={scrollerRef}
                    className="max-h-40 overflow-y-auto rounded-lg border border-input"
                >
                    {items.map((permission) => {
                        const checkboxId = `role-permission-${permission.key}`;
                        return (
                            <label
                                key={permission.key}
                                htmlFor={checkboxId}
                                className="flex cursor-pointer items-center gap-2 border-b border-input px-3 py-2 text-sm last:border-b-0"
                            >
                                <Checkbox
                                    id={checkboxId}
                                    checked={value.includes(permission.key)}
                                    onCheckedChange={(checked) => {
                                        toggle(permission.key, Boolean(checked));
                                    }}
                                />
                                {permission.name}
                            </label>
                        );
                    })}
                    {canLoadMore ? (
                        <div
                            ref={sentinelRef}
                            className="px-3 py-2 text-sm text-muted-foreground"
                        >
                            Loading more…
                        </div>
                    ) : null}
                </div>
            )}
            {error && items.length > 0 ? (
                <PickerError
                    message={error}
                    onRetry={retry}
                />
            ) : null}
        </div>
    );
}

function PickerError({
    message,
    onRetry,
}: {
    message: string;
    onRetry: () => void;
}) {
    return (
        <div className="flex flex-col items-start gap-2">
            <p className="text-sm text-destructive">{message}</p>
            <Button type="button" variant="outline" size="sm" onClick={onRetry}>
                Try again
            </Button>
        </div>
    );
}
