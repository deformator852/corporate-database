import {
    Bot,
    Brain,
    CircleAlert,
    CircleCheck,
    CircleX,
    Database,
    HardDrive,
    ListOrdered,
    RefreshCw,
    Search,
    Server,
    type LucideIcon,
} from "lucide-react";
import {useCallback, useEffect, useState} from "react";

import {Button} from "@/components/ui/button";
import {Card} from "@/components/ui/card";
import {cn} from "cn";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {PageHeader} from "@/shared/ui/PageHeader";
import {documentStatusKey} from "@/entities/document/model";
import type {MessageKey} from "@/shared/i18n/messages";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import type {DocumentStatus} from "@/entities/document/model";
import {getSystemStatus} from "@pages/system/api/system";
import {RechunkNotice} from "@pages/system/ui/RechunkNotice";
import {SYSTEM_REFRESH_MS, type ServiceStatus, type SystemStatus} from "@pages/system/model/system";

const SERVICE_ICONS: Record<string, LucideIcon> = {
    database: Database,
    search_index: Search,
    storage: HardDrive,
    queue: ListOrdered,
    llm: Bot,
    embedding: Brain,
    disk: Server,
};

const STATUS_STYLE: Record<ServiceStatus, {icon: LucideIcon; tone: string}> = {
    ok: {icon: CircleCheck, tone: "text-success"},
    warning: {icon: CircleAlert, tone: "text-warning"},
    down: {icon: CircleX, tone: "text-destructive"},
};

export function SystemStatusPage() {
    const {t} = useI18n();
    const [data, setData] = useState<SystemStatus | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [checkedAt, setCheckedAt] = useState<Date | null>(null);
    const [loading, setLoading] = useState(false);

    // Background refresh; the spinner is only for a manual one.
    const load = useCallback(() => {
        void getSystemStatus()
            .then((next) => {
                setData(next);
                setError(null);
                setCheckedAt(new Date());
            })
            .catch((reason) => setError(getApiErrorMessage(reason, t("system.loadError"))))
            .finally(() => setLoading(false));
    }, [t]);

    useEffect(() => {
        load();
        const timer = window.setInterval(load, SYSTEM_REFRESH_MS);
        return () => window.clearInterval(timer);
    }, [load]);

    const problems = data?.services.filter((service) => service.status !== "ok").length ?? 0;

    return (
        <div className="stack stack--lg w-full">
            <PageHeader
                title={t("system.title")}
                subtitle={t("system.subtitle")}
                action={
                    <div className="flex items-center gap-3">
                        {checkedAt ? (
                            <span className="text-xs text-muted-foreground tabular-nums">
                                {t("system.checkedAt", {time: checkedAt.toLocaleTimeString()})}
                            </span>
                        ) : null}
                        <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={loading}
                            onClick={() => {
                                setLoading(true);
                                load();
                            }}
                        >
                            <RefreshCw className={cn(loading && "animate-spin")} aria-hidden />
                            {t("system.refresh")}
                        </Button>
                    </div>
                }
            />

            {error ? (
                <div role="alert" className="rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">
                    {error}
                </div>
            ) : null}

            {data ? (
                <>
                    <div
                        className={cn(
                            "flex items-center gap-2 rounded-xl px-4 py-3 text-sm font-medium ring-1",
                            problems === 0
                                ? "bg-success/10 text-success ring-success/20"
                                : "bg-warning/10 text-warning ring-warning/20",
                        )}
                    >
                        {problems === 0 ? <CircleCheck className="size-4" aria-hidden /> : <CircleAlert className="size-4" aria-hidden />}
                        {problems === 0 ? t("system.allOk") : t("system.problems", {count: problems})}
                    </div>

                    <section aria-labelledby="services-heading" className="stack">
                        <h2 id="services-heading" className="text-lg">{t("system.services")}</h2>
                        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                            {data.services.map((service) => {
                                const Icon = SERVICE_ICONS[service.name] ?? Server;
                                const {icon: StatusIcon, tone} = STATUS_STYLE[service.status];
                                return (
                                    <Card key={service.name} className="flex-row items-start gap-3 px-4 py-4">
                                        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                                            <Icon className="size-4.5" aria-hidden />
                                        </span>
                                        <div className="min-w-0 flex-1 space-y-0.5">
                                            <p className="flex items-center justify-between gap-2 font-medium">
                                                {t(`system.service.${service.name}` as MessageKey)}
                                                <span className={cn("inline-flex items-center gap-1 text-xs font-medium", tone)}>
                                                    <StatusIcon className="size-3.5" aria-hidden />
                                                    {t(`system.status.${service.status}` as MessageKey)}
                                                </span>
                                            </p>
                                            {service.detail ? (
                                                <p className="text-sm break-words text-muted-foreground">{service.detail}</p>
                                            ) : null}
                                        </div>
                                    </Card>
                                );
                            })}
                        </div>
                    </section>

                    <RechunkNotice
                        outdated={data.outdated_chunks}
                        size={data.config.chunk_size}
                        overlap={data.config.chunk_overlap}
                        onStarted={load}
                    />

                    <div className="grid gap-4 lg:grid-cols-2">
                        <section aria-labelledby="documents-heading" className="stack">
                            <h2 id="documents-heading" className="text-lg">{t("system.documents")}</h2>
                            <Card className="gap-0 px-4 py-2">
                                {Object.keys(data.documents).length === 0 ? (
                                    <p className="py-2 text-sm text-muted-foreground">{t("system.noDocuments")}</p>
                                ) : (
                                    <dl className="divide-y">
                                        {Object.entries(data.documents).map(([status, count]) => (
                                            <div key={status} className="flex justify-between py-2 text-sm">
                                                <dt>{t(documentStatusKey(status as DocumentStatus))}</dt>
                                                <dd className="font-medium tabular-nums">{count}</dd>
                                            </div>
                                        ))}
                                    </dl>
                                )}
                            </Card>
                        </section>
                        <section aria-labelledby="config-heading" className="stack">
                            <h2 id="config-heading" className="text-lg">{t("system.configuration")}</h2>
                            <Card className="gap-0 px-4 py-2">
                                <dl className="divide-y">
                                    {(
                                        [
                                            ["system.config.language", data.config.language],
                                            ["system.config.llm", `${data.config.llm_model} · ${data.config.llm_context}`],
                                            ["system.config.embedding", data.config.embedding_model],
                                            ["system.config.chunks", `${data.config.chunk_size} / ${data.config.chunk_overlap}`],
                                            ["system.config.cleanup", data.config.text_cleanup],
                                        ] as [MessageKey, string][]
                                    ).map(([label, value]) => (
                                        <div key={label} className="flex justify-between gap-4 py-2 text-sm">
                                            <dt className="text-muted-foreground">{t(label)}</dt>
                                            <dd className="truncate text-right font-medium">{value}</dd>
                                        </div>
                                    ))}
                                </dl>
                            </Card>
                        </section>
                    </div>
                </>
            ) : !error ? (
                <p className="text-muted-foreground">{t("common.loading")}</p>
            ) : null}
        </div>
    );
}
