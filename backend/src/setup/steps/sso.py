import shutil
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from ..env import ENV_PATH, env_value, remove_env, upsert_env

CA_COPY = ENV_PATH.parents[1] / "deploy" / "sso" / "ca.pem"
_KEYS = (
    "OIDC_ISSUER",
    "OIDC_CLIENT_ID",
    "OIDC_CLIENT_SECRET",
    "OIDC_REDIRECT_URI",
    "OIDC_NAME",
    "OIDC_GROUPS_CLAIM",
    "OIDC_ROLE_MAP",
    "OIDC_LINK_BY_EMAIL",
    "OIDC_CACERT",
    "PASSWORD_SIGN_IN",  # an older setting: passwords are now off whenever SSO is on
)


def _on(value: str | None, default: bool) -> bool:
    return default if not value else value.lower() in {"1", "true", "yes", "on"}


class SsoStep:
    title = "Sign-in"

    def current(self) -> str | None:
        """None while SSO is off: its first question already defaults to off."""
        issuer = env_value(ENV_PATH, "OIDC_ISSUER")
        if not issuer:
            return None
        return f"single sign-on with {env_value(ENV_PATH, 'OIDC_NAME') or 'SSO'} ({issuer})"

    def run(self, console: Console) -> None:
        console.print(
            "Users can sign in with their company account (single sign-on through Microsoft Entra ID, "
            "ADFS, Keycloak, Okta or another OpenID Connect provider) instead of a Corpus password."
        )
        console.print(
            "With single sign-on on, only administrators sign in with a Corpus password (a link on the "
            "sign-in page), so they can get in when the company's sign-in server is down; everyone else "
            "uses the company account."
        )
        current = env_value(ENV_PATH, "OIDC_ISSUER")
        if not Confirm.ask("Use single sign-on?", default=bool(current), console=console):
            for key in _KEYS:
                remove_env(ENV_PATH, key)
            console.print("Single sign-on is off: users sign in with Corpus passwords.")
            return

        def ask(key: str, label: str, default: str = "") -> str:
            value = Prompt.ask(label, default=env_value(ENV_PATH, key) or default or None, console=console)
            return (value or "").strip()

        while not (issuer := ask("OIDC_ISSUER", "Issuer address (https://…)").rstrip("/")).startswith("https://"):
            console.print("Enter the provider's https:// issuer address, as its discovery document names it.")
        upsert_env(ENV_PATH, "OIDC_ISSUER", issuer)
        ca = ask("OIDC_CACERT", "CA file of the provider's certificate (empty: public CAs)")
        if ca:
            if Path(ca).resolve() != CA_COPY.resolve():
                CA_COPY.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ca, CA_COPY)
            upsert_env(ENV_PATH, "OIDC_CACERT", str(CA_COPY))
        else:
            remove_env(ENV_PATH, "OIDC_CACERT")
        upsert_env(ENV_PATH, "OIDC_CLIENT_ID", ask("OIDC_CLIENT_ID", "Client ID"))
        # Hidden, and never shown as the default: it is a password.
        has_secret = bool(env_value(ENV_PATH, "OIDC_CLIENT_SECRET"))
        secret = Prompt.ask(
            # Hidden like a password: say so, or typing looks broken.
            "Client secret (hidden while you type or paste" + ("; Enter keeps the current one)" if has_secret else ")"),
            password=True,
            default="",
            show_default=False,
            console=console,
        ).strip()
        if secret:
            upsert_env(ENV_PATH, "OIDC_CLIENT_SECRET", secret)
        site = env_value(ENV_PATH, "SITE_ADDRESS") or "corpus.example.com"
        redirect = ask("OIDC_REDIRECT_URI", "Callback address", f"https://{site}/api/v1/auth/sso/callback")
        upsert_env(ENV_PATH, "OIDC_REDIRECT_URI", redirect)
        upsert_env(ENV_PATH, "OIDC_NAME", ask("OIDC_NAME", 'Button name ("Sign in with …")', "Microsoft"))
        upsert_env(ENV_PATH, "OIDC_GROUPS_CLAIM", ask("OIDC_GROUPS_CLAIM", "Groups claim in the ID token", "groups"))
        console.print(
            "Roles from groups: GROUP=ROLE_KEY pairs separated by ';', for example "
            "Corpus Admins=admin;Legal=legal. Mapped roles follow the groups at every sign-in. "
            "Empty: administrators assign roles on the Users page."
        )
        role_map = ask("OIDC_ROLE_MAP", "Group to role map")
        if role_map:
            upsert_env(ENV_PATH, "OIDC_ROLE_MAP", role_map)
        else:
            remove_env(ENV_PATH, "OIDC_ROLE_MAP")
        console.print(
            "People who already have a Corpus account (made with a password) can keep it: at their first "
            "SSO sign-in, the account with the same email becomes theirs, with its roles and chats. Say yes "
            "only if your IT department assigns the emails at the provider. Where people choose their own "
            "email, someone could take over another person's account this way. With no, such a sign-in is "
            "refused until an administrator sorts it out."
        )
        link = Confirm.ask(
            "Link existing Corpus accounts by email?",
            default=_on(env_value(ENV_PATH, "OIDC_LINK_BY_EMAIL"), False),
            console=console,
        )
        upsert_env(ENV_PATH, "OIDC_LINK_BY_EMAIL", "on" if link else "off")
        console.print(
            Panel(
                f"Register Corpus at the provider as a confidential web application:\n"
                f"  redirect URI: {redirect}\n"
                f"  scopes: openid email profile\n"
                f"  ID token: include the groups claim if roles come from groups",
                title="At the provider",
            )
        )
