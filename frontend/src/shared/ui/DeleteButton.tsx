import {Trash2} from "lucide-react";
import type {ComponentProps} from "react";

import {Button} from "@/components/ui/button";
import {useI18n} from "@/shared/i18n/I18nProvider";

/**
 * The one look of a delete action everywhere: red, trash icon, "Delete".
 * `sm` in table rows, cards and action groups; the default size in a page's
 * header. `aria-label` names what goes ("Delete chat Travel budget?").
 */
export function DeleteButton({
    size = "sm",
    children,
    ...props
}: Omit<ComponentProps<typeof Button>, "variant" | "type" | "size"> & {size?: "sm" | "default"}) {
    const {t} = useI18n();
    return (
        <Button type="button" variant="destructive" size={size} {...props}>
            <Trash2 aria-hidden />
            {children ?? t("common.delete")}
        </Button>
    );
}
