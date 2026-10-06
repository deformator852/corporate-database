import {uploadDocument} from "@pages/documents/api/documents";
import {fileStem, type DocumentListItem} from "@pages/documents/model/documents";
import type {DocumentClassification} from "@/entities/document/model";
import {getApiErrorCode, getApiErrorMessage} from "@/shared/lib/api/errors";

type UploadBatch = {
    files: File[];
    /** The typed name, used when there is one file; several are named after themselves. */
    name: string;
    classification: DocumentClassification;
    errorFallback: string;
    onProgress: (sent: number) => void;
    onUploaded?: (document: DocumentListItem) => void;
};

/** Uploads one file at a time: the server checks and converts each, and one
 * failing leaves the others to go on. Returns the files that failed, with
 * their reasons, and whether any was converted to .docx. */
export async function uploadFiles({
    files,
    name,
    classification,
    errorFallback,
    onProgress,
    onUploaded,
}: UploadBatch): Promise<{failed: Map<File, string>; converted: boolean}> {
    const failed = new Map<File, string>();
    let converted = false;
    for (const [index, file] of files.entries()) {
        onProgress(index);
        try {
            const accepted = await uploadDocument(files.length === 1 ? name : fileStem(file.name), file, classification);
            converted ||= accepted.converted === true;
            onUploaded?.(accepted);
        } catch (error) {
            const message = getApiErrorMessage(error, errorFallback);
            failed.set(file, message);
            if (getApiErrorCode(error) === "rate_limited") {
                // Too many documents wait for processing: the rest would be
                // refused the same way.
                for (const rest of files.slice(index + 1)) {
                    failed.set(rest, message);
                }
                break;
            }
        }
    }
    return {failed, converted};
}
