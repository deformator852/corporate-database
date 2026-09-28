import {StrictMode} from "react";
import {createRoot} from "react-dom/client";
import "./index.css";
import {RouterProvider} from "react-router/dom";
import router from "./router";
import {I18nProvider} from "@/shared/i18n/I18nProvider";
import {ThemeProvider} from "./theme/ThemeProvider";
import "@/shared/lib/api/client";

createRoot(document.getElementById("root")!).render(
    <StrictMode>
        <I18nProvider>
            <ThemeProvider>
                <RouterProvider router={router}/>
            </ThemeProvider>
        </I18nProvider>
    </StrictMode>,
);
