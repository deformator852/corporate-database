import {Link} from "react-router";

import {buttonVariants} from "@/components/ui/button";

export default function NotFound() {
    return (
        <div className="flex flex-1 flex-col items-center justify-center gap-4 py-10 text-center">
            <p className="text-sm font-medium text-muted-foreground">404</p>
            <div className="stack items-center">
                <h1>Page not found</h1>
                <p className="max-w-md text-muted-foreground">
                    This page does not exist or you do not have access to it.
                </p>
            </div>
            <Link to="/" className={buttonVariants({size: "lg"})}>
                Back to home
            </Link>
        </div>
    );
}
