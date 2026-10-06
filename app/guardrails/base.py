from typing import Any, Callable, NoReturn, Optional

from agno.exceptions import CheckTrigger, InputCheckError
from agno.guardrails import BaseGuardrail
from agno.run.agent import RunInput

from app.events import record


class Guardrail(BaseGuardrail):
    """Input guardrail base: subclasses set `number`/`name` and implement `check`."""

    number: int = 0
    name: str = ""

    def check(self, run_input: RunInput) -> None:
        raise NotImplementedError

    async def async_check(self, run_input: RunInput) -> None:
        self.check(run_input)

    def block(
        self,
        message: str,
        detail: str = "",
        trigger: CheckTrigger = CheckTrigger.INPUT_NOT_ALLOWED,
        data: Optional[dict] = None,
    ) -> NoReturn:
        record(self.number, self.name, "blocked", detail or message)
        raise InputCheckError(message, check_trigger=trigger, additional_data=data)

    def note(self, action: str, detail: str = "") -> None:
        record(self.number, self.name, action, detail)


def model_check(number: int, name: str, fn: Callable[[], Any], fail_closed: bool, message: str) -> Any:
    """Run a model-backed check. On provider failure either block (fail closed) or log and skip (fail open)."""
    try:
        return fn()
    except InputCheckError:
        raise
    except Exception as exc:
        if fail_closed:
            record(number, name, "blocked", f"check unavailable ({type(exc).__name__}), failing closed")
            raise InputCheckError(message, check_trigger=CheckTrigger.INPUT_NOT_ALLOWED)
        record(number, name, "skipped", f"check unavailable ({type(exc).__name__}), failing open")
        return None
