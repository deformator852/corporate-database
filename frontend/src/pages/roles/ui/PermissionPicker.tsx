import {getPermissionsPage} from "@/entities/permission/api";
import {useI18n} from "@/shared/i18n/I18nProvider";
import {SearchablePicker} from "@/shared/ui/SearchablePicker";

type PermissionPickerProps = {
    value: string[];
    onChange: (keys: string[]) => void;
    enabled: boolean;
};

export function PermissionPicker(props: PermissionPickerProps) {
    const {t} = useI18n();
    return (
        <SearchablePicker
            {...props}
            idPrefix="role-permission"
            loadPage={getPermissionsPage}
            labels={{
                search: t("roles.permissionPicker.search"),
                loading: t("permissions.loading"),
                loadError: t("roles.permissionPicker.loadError"),
                empty: t("roles.permissionPicker.empty"),
                emptySearch: t("roles.permissionPicker.emptySearch"),
            }}
        />
    );
}
