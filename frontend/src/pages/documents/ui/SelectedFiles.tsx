import {X} from "lucide-react";

import {Button} from "@/components/ui/button";
import {NativeSelect} from "@/components/ui/native-select";
import {documentClassificationKey, type DocumentClassification} from "@/entities/document/model";
import {useI18n} from "@/shared/i18n/I18nProvider";

type SelectedFilesProps = {
    files: File[];
    /** Why each file was refused, by the form or by the server. */
    problemOf: (file: File, index: number) => string | undefined;
    /** Levels the user may give. */
    classifications: DocumentClassification[];
    classificationOf: (file: File) => DocumentClassification;
    onClassificationChange: (file: File, classification: DocumentClassification) => void;
    disabled: boolean;
    onRemove: (file: File) => void;
};

/** The files chosen for one upload, each with its problem, its access level and a remove button. */
export function SelectedFiles({
    files,
    problemOf,
    classifications,
    classificationOf,
    onClassificationChange,
    disabled,
    onRemove,
}: SelectedFilesProps) {
    const {t} = useI18n();
    return (
        <ul className="max-h-60 list-none divide-y overflow-y-auto rounded-lg border ps-0">
            {files.map((file, index) => {
                const problem = problemOf(file, index);
                return (
                    <li
                        key={`${file.name}-${file.size}-${file.lastModified}-${index}`}
                        className="flex items-start gap-2 px-3 py-2 text-sm"
                    >
                        <div className="min-w-0 flex-1">
                            <p className="truncate" title={file.name}>
                                {file.name}
                            </p>
                            {problem ? <p className="text-error">{problem}</p> : null}
                        </div>
                        <NativeSelect
                            size="sm"
                            className="shrink-0"
                            disabled={disabled}
                            aria-label={t("documents.upload.accessFor", {name: file.name})}
                            value={classificationOf(file)}
                            onChange={(event) =>
                                onClassificationChange(file, event.target.value as DocumentClassification)
                            }
                        >
                            {classifications.map((value) => (
                                <option key={value} value={value}>
                                    {t(documentClassificationKey(value))}
                                </option>
                            ))}
                        </NativeSelect>
                        <Button
                            type="button"
                            variant="ghost"
                            size="icon-xs"
                            disabled={disabled}
                            aria-label={t("documents.upload.remove", {name: file.name})}
                            onClick={() => onRemove(file)}
                        >
                            <X aria-hidden />
                        </Button>
                    </li>
                );
            })}
        </ul>
    );
}
