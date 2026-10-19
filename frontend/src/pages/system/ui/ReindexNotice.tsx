import {RefreshCw} from "lucide-react";
import {useState} from "react";

import {Button} from "@/components/ui/button";
import {Card} from "@/components/ui/card";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {can} from "@/shared/lib/api/me";
import {ConfirmDialog} from "@/shared/ui/ConfirmDialog";
import {reindexDocuments} from "@pages/system/api/system";

/** The embedding model was changed: search is off until an admin has every
 * document embedded again with it. */
export function ReindexNotice({outdated, onStarted}: {outdated: boolean; onStarted: () => void}) {
    const {t} = useI18n();
    const [confirming, setConfirming] = useState(false);
    const [started, setStarted] = useState<number | null>(null);

    if (started !== null) {
        return (
            <p role="status" className="text-sm text-muted-foreground">
                {t("system.reindex.started", {count: started})}
            </p>
        );
    }
    if (!outdated) {
        return null;
    }
    return (
        <Card className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm">{t("system.reindex.outdated")}</p>
            {can("system.rechunk") ? (
                <Button type="button" size="sm" className="shrink-0" onClick={() => setConfirming(true)}>
                    <RefreshCw aria-hidden />
                    {t("system.reindex.action")}
                </Button>
            ) : null}
            <ConfirmDialog
                open={confirming}
                onOpenChange={setConfirming}
                title={t("system.reindex.title")}
                description={t("system.reindex.description")}
                confirmLabel={t("system.reindex.confirm")}
                pendingLabel={t("system.reindex.pending")}
                errorMessage={t("system.reindex.error")}
                onConfirm={async () => {
                    setStarted(await reindexDocuments());
                    onStarted();
                }}
            />
        </Card>
    );
}
