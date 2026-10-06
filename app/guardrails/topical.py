"""#3 Topical guardrail: keep the assistant inside its domain."""

from agno.exceptions import CheckTrigger
from agno.run.agent import RunInput

from app.guardrails.base import Guardrail, model_check
from app.llm import judge


class TopicalGuardrail(Guardrail):
    number, name = 3, "Topical restriction"

    def __init__(self, domain: str, fail_closed: bool = False):
        self.domain = domain
        self.fail_closed = fail_closed

    def check(self, run_input: RunInput) -> None:
        message = f"I can only help with {self.domain}. Please ask something in that area."
        verdict = model_check(
            self.number,
            self.name,
            lambda: judge(
                f"An assistant is only allowed to discuss: {self.domain}. Greetings, thanks and questions "
                "about what the assistant can do are ON_TOPIC. Is the user's message within that scope? "
                f"Answer only ON_TOPIC or OFF_TOPIC.\n\nMessage: {run_input.input_content_string()}"
            ),
            self.fail_closed,
            message,
        )
        if verdict and "OFF_TOPIC" in verdict:
            self.block(message, detail="judge: OFF_TOPIC", trigger=CheckTrigger.OFF_TOPIC)
