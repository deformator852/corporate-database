import {getRolesPage} from "@/entities/role/api";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {SearchablePicker} from "@/shared/ui/SearchablePicker";

type RolePickerProps = {
    value: string[];
    onChange: (keys: string[]) => void;
    enabled: boolean;
    /** Roles that stay assigned, e.g. Admin on the last administrator. */
    lockedKeys?: string[];
    lockedReason?: string;
};

export function RolePicker(props: RolePickerProps) {
    const {t} = useI18n();
    return (
        <SearchablePicker
            {...props}
            idPrefix="user-role"
            loadPage={getRolesPage}
            labels={{
                search: t("users.rolePicker.search"),
                loading: t("roles.loading"),
                loadError: t("users.rolePicker.loadError"),
                empty: t("users.rolePicker.empty"),
                emptySearch: t("users.rolePicker.emptySearch"),
            }}
        />
    );
}
