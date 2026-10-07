import {ExternalLink, FileText} from "lucide-react";
import {useState} from "react";

import {Button} from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import type {ChatSource} from "@/entities/chat/model";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import {getDocumentChunk, openDocumentFile, type DocumentChunk} from "@/shared/lib/documentFile";

type Quote = {source: ChatSource; status: "loading"} | {source: ChatSource; status: "ready"; chunk: DocumentChunk} | {source: ChatSource; status: "error"; message: string};

/** The documents an answer used. One with a quoted passage opens it, with
 * the answer's words marked; the file opens from there (a PDF at the page). */
export function SourceList({sources, answer = ""}: {sources: ChatSource[]; answer?: string}) {
    const {t} = useI18n();
    const [error, setError] = useState<string | null>(null);
    const [quote, setQuote] = useState<Quote | null>(null);

    const openFile = (source: ChatSource, page?: number | null) => {
        setError(null);
        void openDocumentFile(source.id, source.filename, page).catch((reason) =>
            setError(getApiErrorMessage(reason, t("documents.openError"))),
        );
    };

    const open = (source: ChatSource) => {
        if (source.chunk == null) {
            openFile(source);
            return;
        }
        setQuote({source, status: "loading"});
        void getDocumentChunk(source.id, source.chunk)
            .then((chunk) => setQuote((current) => (current?.source === source ? {source, status: "ready", chunk} : current)))
            .catch((reason) =>
                setQuote((current) =>
                    current?.source === source
                        ? {source, status: "error", message: getApiErrorMessage(reason, t("chat.quote.error"))}
                        : current,
                ),
            );
    };

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
                        onClick={() => open(source)}
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

            <Dialog open={quote != null} onOpenChange={(next) => !next && setQuote(null)}>
                <DialogContent className="sm:max-w-2xl" showCloseButton>
                    <DialogHeader>
                        <DialogTitle className="break-words">{quote?.source.name}</DialogTitle>
                        <DialogDescription>
                            {quote?.status === "ready" && quote.chunk.page != null
                                ? t("chat.quote.fromPage", {page: quote.chunk.page})
                                : t("chat.quote.description")}
                        </DialogDescription>
                    </DialogHeader>
                    {quote?.status === "loading" ? (
                        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
                    ) : quote?.status === "error" ? (
                        <p role="alert" className="text-sm text-destructive">
                            {quote.message}
                        </p>
                    ) : quote?.status === "ready" ? (
                        <blockquote className="max-h-[60vh] overflow-y-auto rounded-lg border-l-4 bg-muted/50 px-4 py-3 text-sm break-words whitespace-pre-wrap">
                            {highlighted(quote.chunk.text, answer)}
                        </blockquote>
                    ) : null}
                    <DialogFooter>
                        {quote ? (
                            <Button
                                type="button"
                                variant="outline"
                                onClick={() => openFile(quote.source, quote.status === "ready" ? quote.chunk.page : null)}
                            >
                                <ExternalLink aria-hidden />
                                {t("chat.quote.openFile")}
                            </Button>
                        ) : null}
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}

// Words that carry a fact, as the server judges sources (answer_sources.py):
// numbers and words of five letters or more.
const WORD = /[\p{L}\p{N}_]+/gu;

function factWords(text: string): Set<string> {
    return new Set(
        (text.match(WORD) ?? [])
            .filter((word) => word.length >= 5 || /^\p{N}+$/u.test(word))
            .map((word) => word.toLowerCase()),
    );
}

/** `text` with the words it shares with `answer` marked. */
function highlighted(text: string, answer: string) {
    const wanted = factWords(answer);
    if (wanted.size === 0) {
        return text;
    }
    const parts: (string | React.JSX.Element)[] = [];
    let last = 0;
    for (const match of text.matchAll(WORD)) {
        if (!wanted.has(match[0].toLowerCase())) {
            continue;
        }
        parts.push(text.slice(last, match.index));
        parts.push(
            <mark key={match.index} className="rounded-sm bg-yellow-200/70 px-0.5 text-foreground dark:bg-yellow-500/30">
                {match[0]}
            </mark>,
        );
        last = match.index + match[0].length;
    }
    parts.push(text.slice(last));
    return parts;
}
