import {useSearchParams} from "react-router";

/** The `page` URL parameter (1 when absent or invalid) and a way to move. */
export function usePageParam(): [number, (page: number) => void] {
    const [searchParams, setSearchParams] = useSearchParams();
    const raw = Number(searchParams.get("page"));
    const page = Number.isInteger(raw) && raw >= 1 ? raw : 1;
    const goToPage = (next: number) =>
        setSearchParams((current) => {
            const params = new URLSearchParams(current);
            if (next <= 1) {
                params.delete("page");
            } else {
                params.set("page", String(next));
            }
            return params;
        });
    return [page, goToPage];
}

/** After deleting a row of `page`: the page before when that row was the
 * only one shown (the page is now empty), otherwise `page` again. */
export function refreshAfterDelete(
    page: number,
    rowsShown: number,
    goToPage: (page: number) => void,
    reload: () => void,
): void {
    if (rowsShown === 1 && page > 1) {
        goToPage(page - 1);
    } else {
        reload();
    }
}
