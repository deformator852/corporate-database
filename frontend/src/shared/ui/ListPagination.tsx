import {Button} from "@/components/ui/button";
import {useI18n} from "@/shared/i18n/I18nProvider";

type ListPaginationProps = {
    page: number;
    pages: number;
    perPage: number;
    total: number;
    /** Items on this page. */
    shown: number;
    onPageChange: (page: number) => void;
};

/** "Showing 21-40 of 95" with previous and next. */
export function ListPagination({page, pages, perPage, total, shown, onPageChange}: ListPaginationProps) {
    const {t} = useI18n();
    const from = total === 0 ? 0 : (page - 1) * perPage + 1;
    const to = total === 0 ? 0 : (page - 1) * perPage + shown;
    return (
        <nav
            aria-label={t("common.pagination")}
            className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
        >
            <p className="text-sm text-muted-foreground">{t("common.showing", {from, to, total})}</p>
            <div className="flex items-center gap-2">
                <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => onPageChange(page - 1)}
                >
                    {t("common.previous")}
                </Button>
                <p className="min-w-24 text-center text-sm text-muted-foreground">
                    {t("common.pageOf", {page, pages: Math.max(pages, 1)})}
                </p>
                <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={pages === 0 || page >= pages}
                    onClick={() => onPageChange(page + 1)}
                >
                    {t("common.next")}
                </Button>
            </div>
        </nav>
    );
}
