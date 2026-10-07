import {FileText} from "lucide-react";
import {useState} from "react";

import type {ChatSource} from "@/entities/chat/model";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {openDocumentFile} from "@/shared/lib/documentFile";

/** The documents an answer used; each opens the file. */
export function SourceList({sources}: {sources: ChatSource[]}) {
    const {t} = useI18n();
    const [error, setError] = useState<string | null>(null);
    return (
        <div className="mr-auto flex max-w-[min(100%,48rem)] flex-col gap-1.5">
            <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-xs text-muted-foreground">{t("chat.sources")}</span>
                {sources.map((source) => (
                    <button
                        key={source.id}
                        type="button"
                        title={source.filename}
                        aria-label={t("chat.openSource", {name: source.name})}
                        onClick={() => {
                            setError(null);
                            void openDocumentFile(source.id, source.filename).catch((reason) =>
                                setError(getApiErrorMessage(reason, t("documents.openError"))),
                            );
                        }}
                        className="inline-flex max-w-64 cursor-pointer items-center gap-1.5 rounded-full border bg-background px-2.5 py-1 text-xs font-medium outline-none transition-colors hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
                    >
                        <FileText className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                        <span className="truncate">{source.name}</span>
                    </button>
                ))}
            </div>
            {error ? (
                <p role="alert" className="text-xs text-destructive">
                    {error}
                </p>
            ) : null}
        </div>
    );
}
