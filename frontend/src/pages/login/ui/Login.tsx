import { Database } from "lucide-react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Field,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ThemeSwitcher } from "@/theme/ThemeSwitcher";

export default function Login() {
  return (
    <div className="relative flex min-h-svh flex-col items-center justify-center bg-muted/30 px-4 py-10">
      <div className="absolute top-4 right-4">
        <ThemeSwitcher />
      </div>
      <div className="mb-8 flex flex-col items-center gap-3 text-center">
        <div
          className="flex size-11 items-center justify-center rounded-lg bg-primary text-primary-foreground"
          aria-hidden
        >
          <Database className="size-5" strokeWidth={2} />
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
          <form
            className="contents"
            onSubmit={(event) => {
              event.preventDefault();
            }}
          >
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="login-email">Email</FieldLabel>
                <Input
                  id="login-email"
                  name="email"
                  type="email"
                  placeholder="name@company.com"
                  autoComplete="email"
                  required
                />
              </Field>

              <Field>
                <FieldLabel htmlFor="login-password">Password</FieldLabel>
                <Input
                  id="login-password"
                  name="password"
                  type="password"
                  placeholder="••••••••"
                  autoComplete="current-password"
                  required
                />
              </Field>

              <div className="flex items-center justify-between gap-4 text-sm">
                <label className="flex cursor-pointer items-center gap-2 text-muted-foreground">
                  <input
                    type="checkbox"
                    name="remember"
                    className="size-3.5 rounded border border-input accent-primary"
                  />
                  Remember me
                </label>
                <Button type="button" variant="link" className="h-auto px-0">
                  Forgot password?
                </Button>
              </div>

              <Button type="submit" className="mt-1 w-full" size="lg">
                Sign in
              </Button>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>

      <p className="mt-8 text-center text-sm text-muted-foreground">
        No access?{" "}
        <Button variant="link" className="h-auto px-1" render={<Link to="/" />}>
          Back to home
        </Button>
      </p>
    </div>
  );
}
