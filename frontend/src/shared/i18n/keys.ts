import type {DocumentClassification, DocumentStatus} from "@pages/documents/model/documents";
import type {NotificationType} from "@/widgets/notifications/model/notifications";

import type {MessageKey} from "./messages";

export function documentClassificationKey(
    value: DocumentClassification,
): MessageKey {
    return `documents.classification.${value}` as MessageKey;
}

export function documentStatusKey(value: DocumentStatus): MessageKey {
    return `documents.status.${value}` as MessageKey;
}

export function notificationTypeKey(type: NotificationType): MessageKey {
    return `notifications.type.${type}` as MessageKey;
}
