import {Scissors} from "lucide-react";
import {useState} from "react";

import {Button} from "@/components/ui/button";
import {Card} from "@/components/ui/card";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {can} from "@/shared/lib/api/me";
import {ConfirmDialog} from "@/shared/ui/ConfirmDialog";
import {rechunkDocuments} from "@pages/system/api/system";

/** Documents cut with another chunk size than the current one: they keep
 * working as they are; an admin may cut them again. */
export function RechunkNotice({
    outdated,
    size,
    overlap,
    onStarted,
}: {
    outdated: number;
    size: number;
    overlap: number;
    onStarted: () => void;
}) {
    const {t} = useI18n();
    const [confirming, setConfirming] = useState(false);
    const [started, setStarted] = useState<number | null>(null);

    if (started !== null) {
        return (
            <p role="status" className="text-sm text-muted-foreground">
                {t("system.rechunk.started", {count: started})}
            </p>
        );
    }
    if (outdated === 0) {
        return null;
    }
    return (
        <Card className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm">{t("system.rechunk.outdated", {count: outdated, size, overlap})}</p>
            {can("system.rechunk") ? (
                <Button type="button" variant="outline" size="sm" className="shrink-0" onClick={() => setConfirming(true)}>
                    <Scissors aria-hidden />
                    {t("system.rechunk.action")}
                </Button>
            ) : null}
            <ConfirmDialog
                open={confirming}
                onOpenChange={setConfirming}
                title={t("system.rechunk.title", {count: outdated})}
                description={t("system.rechunk.description")}
                confirmLabel={t("system.rechunk.confirm")}
                pendingLabel={t("system.rechunk.pending")}
                errorMessage={t("system.rechunk.error")}
                onConfirm={async () => {
                    setStarted(await rechunkDocuments());
                    onStarted();
                }}
            />
        </Card>
    );
}
