import {Link} from "react-router";

import {buttonVariants} from "@/components/ui/button";
import {useI18n} from "@/shared/i18n/I18nProvider";

export default function NotFound() {
    const {t} = useI18n();

    return (
        <div className="flex flex-1 flex-col items-center justify-center gap-4 py-10 text-center">
            <p className="text-sm font-medium text-base-content/70">
                {t("notFound.code")}
            </p>
            <div className="stack items-center">
                <h1>{t("notFound.title")}</h1>
                <p className="max-w-md text-base-content/70">
                    {t("notFound.description")}
                </p>
            </div>
            <Link to="/" className={buttonVariants({size: "lg"})}>
                {t("notFound.backHome")}
            </Link>
        </div>
    );
}
