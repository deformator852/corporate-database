import {useSearchParams} from "react-router";

/** The URL query and a way to change some of its parameters. An empty value,
 * or page 1, is left out of the URL. */
export function useUrlParams(): [URLSearchParams, (changes: Record<string, string>) => void] {
    const [searchParams, setSearchParams] = useSearchParams();
    const update = (changes: Record<string, string>) =>
        setSearchParams((current) => {
            const params = new URLSearchParams(current);
            for (const [name, value] of Object.entries(changes)) {
                if (!value || (name === "page" && value === "1")) {
                    params.delete(name);
                } else {
                    params.set(name, value);
                }
            }
            return params;
        });
    return [searchParams, update];
}
