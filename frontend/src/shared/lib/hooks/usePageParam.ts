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
