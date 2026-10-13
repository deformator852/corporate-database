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
        /** The default first; more when users switch in the header. */
        languages: string[];
        llm_model: string;
        llm_context: number;
        embedding_model: string;
        chunk_size: number;
        chunk_overlap: number;
    };
    /** Completed documents cut with another chunk size or overlap. */
    outdated_chunks: number;
};

export const SYSTEM_REFRESH_MS = 15_000;
