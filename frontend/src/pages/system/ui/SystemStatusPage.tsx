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
import {isLocale, LOCALE_NAMES, type MessageKey} from "@/shared/i18n/messages";
import {getApiErrorMessage} from "@/shared/lib/api/errors";
import type {DocumentStatus} from "@/entities/document/model";
import {getSystemStatus} from "@pages/system/api/system";
import {RechunkNotice} from "@pages/system/ui/RechunkNotice";
import {ReindexNotice} from "@pages/system/ui/ReindexNotice";
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
    down: {icon: CircleX, tone: "text-error"},
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
                            <span className="text-xs text-base-content/70 tabular-nums">
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
                <div role="alert" className="d-alert d-alert-error d-alert-soft text-sm">
                    {error}
                </div>
            ) : null}

            {data ? (
                <>
                    <div
                        className={cn(
                            "d-alert d-alert-soft text-sm font-medium",
                            problems === 0 ? "d-alert-success" : "d-alert-warning",
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
                                        <div className="d-avatar d-avatar-placeholder shrink-0">
                                            <div className="size-9 rounded-lg bg-base-200 text-base-content/70">
                                                <Icon className="size-4.5" aria-hidden />
                                            </div>
                                        </div>
                                        <div className="min-w-0 flex-1 space-y-0.5">
                                            <p className="flex items-center justify-between gap-2 font-medium">
                                                {t(`system.service.${service.name}` as MessageKey)}
                                                <span className={cn("inline-flex items-center gap-1 text-xs font-medium", tone)}>
                                                    <StatusIcon className="size-3.5" aria-hidden />
                                                    {t(`system.status.${service.status}` as MessageKey)}
                                                </span>
                                            </p>
                                            {service.detail ? (
                                                <p className="text-sm break-words text-base-content/70">{service.detail}</p>
                                            ) : null}
                                        </div>
                                    </Card>
                                );
                            })}
                        </div>
                    </section>

                    {data.missing_files ? (
                        <Card role="alert" className="flex-row items-start gap-2 px-4 py-3 text-sm">
                            <CircleAlert className="mt-0.5 size-4 shrink-0 text-error" aria-hidden />
                            {t("system.missingFiles", {count: data.missing_files})}
                        </Card>
                    ) : null}
                    <ReindexNotice outdated={data.outdated_index_model !== null} onStarted={load} />
                    <RechunkNotice outdated={data.outdated_chunks} onStarted={load} />

                    <div className="grid gap-4 lg:grid-cols-2">
                        <section aria-labelledby="documents-heading" className="stack">
                            <h2 id="documents-heading" className="text-lg">{t("system.documents")}</h2>
                            <Card className="gap-0 px-4 py-2">
                                {Object.keys(data.documents).length === 0 ? (
                                    <p className="py-2 text-sm text-base-content/70">{t("system.noDocuments")}</p>
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
                                            ["system.config.version", data.config.version],
                                            ["system.config.language", languageList(data.config.languages, t("system.config.defaultLanguage"))],
                                            ["system.config.llm", `${data.config.llm_model} · ${data.config.llm_context}`],
                                            ["system.config.embedding", data.config.embedding_model],
                                            ["system.config.chunks", `${data.config.chunk_size} / ${data.config.chunk_overlap}`],
                                        ] as [MessageKey, string][]
                                    ).map(([label, value]) => (
                                        <div key={label} className="flex justify-between gap-4 py-2 text-sm">
                                            <dt className="text-base-content/70">{t(label)}</dt>
                                            <dd className="truncate text-right font-medium">{value}</dd>
                                        </div>
                                    ))}
                                </dl>
                            </Card>
                        </section>
                    </div>
                </>
            ) : !error ? (
                <p className="text-base-content/70">{t("common.loading")}</p>
            ) : null}
        </div>
    );
}

/** "English (default), Español": each language in its own name. */
function languageList(codes: string[], defaultMark: string): string {
    return codes
        .map((code, index) => {
            const name = isLocale(code) ? LOCALE_NAMES[code] : code;
            return index === 0 && codes.length > 1 ? `${name} (${defaultMark})` : name;
        })
        .join(", ");
}
