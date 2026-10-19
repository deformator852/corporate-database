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
        /** Corpus's version, e.g. 1.0.0. */
        version: string;
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
    /** Documents with no file in the storage, as of the backend's start. */
    missing_files: number;
    /** The model the index is built with when the configured one differs:
     * search is off until the index is rebuilt. */
    outdated_index_model: string | null;
};

export const SYSTEM_REFRESH_MS = 15_000;
