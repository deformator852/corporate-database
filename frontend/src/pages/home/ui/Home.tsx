import {PanelLeft, SquarePen, X} from "lucide-react";
import {useState} from "react";

import {Button} from "@/components/ui/button";
import {Sheet, SheetClose, SheetContent, SheetTitle, SheetTrigger} from "@/components/ui/sheet";
import {useChat} from "@pages/home/model/useChat";
import {ChatComposer} from "@pages/home/ui/ChatComposer";
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
            disabled={pending}
            onNew={startNewChat}
            onOpen={(id) => {
                setHistoryOpen(false);
                void chat.openConversation(id);
            }}
            onDelete={(id) => void chat.removeConversation(id)}
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
        <div className="flex h-full min-h-0 flex-1 gap-4 overflow-hidden">
            <h1 className="sr-only">{t("chat.title")}</h1>
            {historyShown ? (
                <aside
                    id="chat-history"
                    aria-label={t("chat.history")}
                    className="hidden w-64 shrink-0 overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10 md:block"
                >
                    {history}
                </aside>
            ) : null}
            <section
                aria-label={t("chat.panelLabel")}
                className="relative flex h-full min-h-0 flex-1 flex-col overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10"
            >
                <header className="flex shrink-0 items-center gap-1 border-b border-border px-2 py-1.5">
                    <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="hidden md:inline-flex"
                        aria-label={t(historyShown ? "chat.hideHistory" : "chat.showHistory")}
                        aria-controls="chat-history"
                        aria-expanded={historyShown}
                        onClick={toggleHistory}
                    >
                        <PanelLeft aria-hidden />
                    </Button>
                    <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
                        <SheetTrigger
                            render={
                                <Button
                                    type="button"
                                    variant="ghost"
                                    size="icon"
                                    className="md:hidden"
                                    aria-label={t("chat.showHistory")}
                                />
                            }
                        >
                            <PanelLeft aria-hidden />
                        </SheetTrigger>
                        <SheetContent side="left" showCloseButton={false} className="gap-0 p-0">
                            <div className="flex items-center justify-between border-b px-4 py-2">
                                <SheetTitle>{t("chat.history")}</SheetTitle>
                                <SheetClose
                                    render={<Button type="button" variant="ghost" size="icon" aria-label={t("common.close")} />}
                                >
                                    <X aria-hidden />
                                </SheetClose>
                            </div>
                            <div className="min-h-0 flex-1">{history}</div>
                        </SheetContent>
                    </Sheet>
                    <p className="min-w-0 flex-1 truncate px-1 text-sm font-medium">{t("chat.title")}</p>
                    <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className={historyShown ? "md:hidden" : undefined}
                        aria-label={t("chat.newChat")}
                        disabled={pending}
                        onClick={startNewChat}
                    >
                        <SquarePen aria-hidden />
                    </Button>
                </header>
                <ChatMessages
                    messages={chat.messages}
                    streaming={chat.streaming}
                    status={chat.status}
                    error={chat.error}
                    onRetry={chat.retry}
                    onRate={(message, rating) => void chat.rate(message, rating)}
                />
                <ChatComposer
                    value={chat.draft}
                    pending={pending}
                    onChange={chat.setDraft}
                    onSubmit={chat.submit}
                    onCancel={chat.cancel}
                />
            </section>
        </div>
    );
}

export default Home;
