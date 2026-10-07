import {Search} from "lucide-react";

import {Input} from "@/components/ui/input";
import {NativeSelect, NativeSelectOption} from "@/components/ui/native-select";
import {documentClassificationKey, type DocumentClassification} from "@/entities/document/model";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {
    DOCUMENT_STATUS_FILTERS,
    type DocumentFilters,
    type DocumentStatusFilter,
} from "@pages/documents/model/documents";

type DocumentFilterBarProps = {
    search: string;
    onSearch: (text: string) => void;
    filters: DocumentFilters;
    /** Access levels the user may see. */
    classifications: DocumentClassification[];
    onChange: (changes: Partial<Pick<DocumentFilters, "status" | "classification">>) => void;
};

const STATUS_KEYS = {
    processing: "documents.filter.processing",
    completed: "documents.status.completed",
    failed: "documents.status.failed",
} as const satisfies Record<DocumentStatusFilter, string>;

export function DocumentFilterBar({search, onSearch, filters, classifications, onChange}: DocumentFilterBarProps) {
    const {t} = useI18n();
    return (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="relative flex-1">
                <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
                <Input
                    type="search"
                    value={search}
                    onChange={(event) => onSearch(event.target.value)}
                    placeholder={t("documents.filter.search")}
                    aria-label={t("documents.filter.search")}
                    className="pl-8"
                />
            </div>
            <NativeSelect
                className="w-full sm:w-44"
                aria-label={t("documents.filter.byStatus")}
                value={filters.status}
                onChange={(event) => onChange({status: event.target.value as DocumentFilters["status"]})}
            >
                <NativeSelectOption value="">{t("documents.filter.allStatuses")}</NativeSelectOption>
                {DOCUMENT_STATUS_FILTERS.map((status) => (
                    <NativeSelectOption key={status} value={status}>
                        {t(STATUS_KEYS[status])}
                    </NativeSelectOption>
                ))}
            </NativeSelect>
            <NativeSelect
                className="w-full sm:w-44"
                aria-label={t("documents.filter.byAccess")}
                value={filters.classification}
                onChange={(event) =>
                    onChange({classification: event.target.value as DocumentFilters["classification"]})
                }
            >
                <NativeSelectOption value="">{t("documents.filter.allAccess")}</NativeSelectOption>
                {classifications.map((value) => (
                    <NativeSelectOption key={value} value={value}>
                        {t(documentClassificationKey(value))}
                    </NativeSelectOption>
                ))}
            </NativeSelect>
        </div>
    );
}
