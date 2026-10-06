export type ServiceStatus = "ok" | "warning" | "down";

type ServiceCheck = {
    name: string;
    status: ServiceStatus;
    detail: string;
};

export type SystemStatus = {
    services: ServiceCheck[];
    documents: Record<string, number>;
    config: {
        language: string;
        llm_model: string;
        llm_context: number;
        embedding_model: string;
        chunk_size: number;
        chunk_overlap: number;
        text_cleanup: string;
    };
};

export const SYSTEM_REFRESH_MS = 15_000;
