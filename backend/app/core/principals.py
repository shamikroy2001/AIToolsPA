from dataclasses import dataclass


@dataclass(frozen=True)
class ClerkPrincipal:
    clerk_user_id: str
    email: str = ""
