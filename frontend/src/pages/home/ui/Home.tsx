import {PanelLeft, SquarePen, X} from "lucide-react";
import {useState} from "react";
import {cn} from "cn";

import {Sheet, SheetClose, SheetContent, SheetTitle, SheetTrigger} from "@/components/ui/sheet";
import {useChat} from "@pages/home/model/useChat";
import {can} from "@/shared/lib/api/me";
import {ChatComposer} from "@pages/home/ui/ChatComposer";
import {ChatDocumentPicker} from "@pages/home/ui/ChatDocumentPicker";
import {ChatHistory} from "@pages/home/ui/ChatHistory";
import {ChatMessages} from "@pages/home/ui/ChatMessages";
import {useI18n} from "@/shared/i18n/I18nProvider";

/** Remembers whether the desktop history column is shown. */
const HISTORY_SHOWN_KEY = "chat-history-shown";

function readHistoryShown() {
    try {
        return localStorage.getItem(HISTORY_SHOWN_KEY) !== "0";
    } catch {
        return true;
    }
}

function Home() {
    const {t} = useI18n();
    const chat = useChat();
    // Desktop: a column that can be hidden. Phones: a panel sliding in from the left.
    const [historyShown, setHistoryShown] = useState(readHistoryShown);
    const [historyOpen, setHistoryOpen] = useState(false);

    const startNewChat = () => {
        chat.startNewChat();
        setHistoryOpen(false);
    };

    const pending = chat.status === "pending";
    const history = (
        <ChatHistory
            conversations={chat.conversations}
            error={chat.historyError}
            activeId={chat.conversationId}
            query={chat.historyQuery}
            onSearch={chat.searchHistory}
            disabled={pending}
            onNew={startNewChat}
            onOpen={(id) => {
                setHistoryOpen(false);
                void chat.openConversation(id);
            }}
        />
    );

    function toggleHistory() {
        const next = !historyShown;
        setHistoryShown(next);
        try {
            localStorage.setItem(HISTORY_SHOWN_KEY, next ? "1" : "0");
        } catch {
            // Storage is blocked: the choice lasts until reload.
        }
    }

    return (
        <div className="flex h-full min-h-0 flex-1 gap-4 overflow-hidden text-base-content">
            <h1 className="sr-only">{t("chat.title")}</h1>
            {historyShown ? (
                <aside
                    id="chat-history"
                    aria-label={t("chat.history")}
                    className="d-card d-card-border hidden w-64 shrink-0 overflow-hidden bg-base-100 md:block"
                >
                    {history}
                </aside>
            ) : null}
            <section
                aria-label={t("chat.panelLabel")}
                className="d-card d-card-border relative h-full min-h-0 flex-1 overflow-hidden bg-base-100"
            >
                <header className="d-navbar min-h-0 shrink-0 gap-1 border-b border-base-300 p-1.5">
                    <button
                        type="button"
                        className="d-btn d-btn-ghost d-btn-square d-btn-sm hidden md:inline-flex"
                        aria-label={t(historyShown ? "chat.hideHistory" : "chat.showHistory")}
                        aria-controls="chat-history"
                        aria-expanded={historyShown}
                        onClick={toggleHistory}
                    >
                        <PanelLeft className="size-4" aria-hidden />
                    </button>
                    <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
                        <SheetTrigger
                            render={
                                <button
                                    type="button"
                                    className="d-btn d-btn-ghost d-btn-square d-btn-sm md:hidden"
                                    aria-label={t("chat.showHistory")}
                                />
                            }
                        >
                            <PanelLeft className="size-4" aria-hidden />
                        </SheetTrigger>
                        <SheetContent side="left" showCloseButton={false} className="gap-0 p-0">
                            <div className="flex items-center justify-between border-b px-4 py-2">
                                <SheetTitle>{t("chat.history")}</SheetTitle>
                                <SheetClose
                                    render={<button type="button" className="d-btn d-btn-ghost d-btn-square d-btn-sm" aria-label={t("common.close")} />}
                                >
                                    <X className="size-4" aria-hidden />
                                </SheetClose>
                            </div>
                            <div className="min-h-0 flex-1">{history}</div>
                        </SheetContent>
                    </Sheet>
                    <p className="min-w-0 flex-1 truncate px-1 text-sm font-medium">{t("chat.title")}</p>
                    <button
                        type="button"
                        className={cn("d-btn d-btn-ghost d-btn-square d-btn-sm", historyShown && "md:hidden")}
                        aria-label={t("chat.newChat")}
                        disabled={pending}
                        onClick={startNewChat}
                    >
                        <SquarePen className="size-4" aria-hidden />
                    </button>
                </header>
                <ChatMessages
                    messages={chat.messages}
                    streaming={chat.streaming}
                    status={chat.status}
                    error={chat.error}
                    onRetry={chat.retry}
                    onRate={(message, rating) => void chat.rate(message, rating)}
                    onRegenerate={chat.regenerate}
                />
                <ChatComposer
                    value={chat.draft}
                    pending={pending}
                    onChange={chat.setDraft}
                    onSubmit={chat.submit}
                    onCancel={chat.cancel}
                    toolbar={
                        // The picker lists documents: it needs the right to list them.
                        can("documents.list") ? (
                            <ChatDocumentPicker
                                value={chat.documents}
                                onChange={chat.setDocuments}
                                disabled={pending}
                            />
                        ) : null
                    }
                />
            </section>
        </div>
    );
}

export default Home;
