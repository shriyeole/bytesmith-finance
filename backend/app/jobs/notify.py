"""Where alert digests go. LogNotifier writes to the log (default, no PII beyond counts);
plug in an email provider by implementing Notifier.send_digest."""

import logging
from typing import List, Protocol

log = logging.getLogger("bytesmith.notify")


class Notifier(Protocol):
    def send_digest(self, user_id: str, email: str | None, items: List[dict]) -> bool: ...


class LogNotifier:
    def __init__(self) -> None:
        self.sent: List[dict] = []

    def send_digest(self, user_id: str, email: str | None, items: List[dict]) -> bool:
        # Log counts and rule ids only — never amounts or messages (spec §12.4).
        log.info("alert digest user=%s items=%d rules=%s", user_id, len(items), ",".join(i["rule_id"] for i in items))
        self.sent.append({"user_id": user_id, "email": email, "items": items})
        return True
