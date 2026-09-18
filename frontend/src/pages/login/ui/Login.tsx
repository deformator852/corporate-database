import {Database} from "lucide-react";
import {Card, CardContent, CardDescription, CardHeader, CardTitle,} from "@/components/ui/card";
import {ThemeSwitcher} from "@/theme/ThemeSwitcher";
import {LoginForm} from "@pages/login/ui/LoginForm.tsx";

export default function Login() {
    return (
        <div className="relative flex min-h-svh flex-col items-center justify-center bg-muted/30 px-4 py-10">
            <div className="absolute top-4 right-4">
                <ThemeSwitcher/>
            </div>
            <div className="mb-8 flex flex-col items-center gap-3 text-center">
                <div
                    className="flex size-11 items-center justify-center rounded-lg bg-primary text-primary-foreground"
                    aria-hidden
                >
                    <Database className="size-5" strokeWidth={2}/>
                </div>
                <div className="space-y-1">
                    <p className="font-semibold tracking-tight">Corporate Database</p>
                    <p className="text-sm text-muted-foreground">
                        Internal access to corporate data
                    </p>
                </div>
            </div>

            <Card className="w-full max-w-sm shadow-sm">
                <CardHeader className="border-b">
                    <CardTitle className="text-lg">Sign in</CardTitle>
                    <CardDescription>
                        Enter the credentials provided by your administrator
                    </CardDescription>
                </CardHeader>

                <CardContent className="pt-6">
                    <LoginForm/>
                </CardContent>
            </Card>
        </div>
    );
}
