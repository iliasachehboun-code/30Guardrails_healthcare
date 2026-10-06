"""#7 OpenAI moderation (input + output), #12 output safety judge, #16 crisis safe completion."""

from typing import List, Optional

from agno.exceptions import CheckTrigger, InputCheckError
from agno.guardrails import OpenAIModerationGuardrail
from agno.run.agent import RunInput, RunOutput

from app import config
from app.events import record
from app.guardrails.base import Guardrail, model_check
from app.llm import judge, moderate

REFUSAL = "I can't help with that request."
SAFE_REPLACEMENT = "I'm not able to share that response. Please contact AcmeHealth support if you need help."


class ModerationGuardrail(OpenAIModerationGuardrail):
    """#7 Agno's built-in OpenAI moderation guardrail, made to fail closed and to report its decision."""

    number, name = 7, "OpenAI moderation (input)"

    def __init__(self, raise_for_categories: Optional[List[str]] = None):
        super().__init__(
            moderation_model=config.MODERATION_MODEL,
            raise_for_categories=raise_for_categories,
            api_key=config.OPENAI_API_KEY,
        )

    def check(self, run_input: RunInput) -> None:
        try:
            super().check(run_input)
        except InputCheckError as exc:
            categories = [k for k, v in (exc.additional_data or {}).get("categories", {}).items() if v]
            record(self.number, self.name, "blocked", "flagged: " + ", ".join(categories))
            raise InputCheckError(REFUSAL, check_trigger=CheckTrigger.INPUT_NOT_ALLOWED, additional_data=exc.additional_data)
        except Exception as exc:
            record(self.number, self.name, "blocked", f"moderation unavailable ({type(exc).__name__}), failing closed")
            raise InputCheckError("Safety check unavailable, please try again later.")

    async def async_check(self, run_input: RunInput) -> None:
        self.check(run_input)


class OutputModeration:
    """#7 Run the final answer through OpenAI moderation and replace it if flagged."""

    number, name = 7, "OpenAI moderation (output)"

    def __call__(self, run_output: RunOutput) -> None:
        if not isinstance(run_output.content, str) or not run_output.content:
            return
        try:
            flagged = moderate(run_output.content)
        except Exception as exc:
            record(self.number, self.name, "modified", f"moderation unavailable ({type(exc).__name__}), withheld")
            run_output.content = SAFE_REPLACEMENT
            return
        if flagged:
            record(self.number, self.name, "modified", "flagged: " + ", ".join(flagged))
            run_output.content = SAFE_REPLACEMENT


class OutputSafetyJudge:
    """#12 Domain-aware output check: catches answers that are unsafe for *this* product
    (e.g. specific dosing beyond label guidance) even if they pass generic moderation."""

    number, name = 12, "Output safety judge"

    def __init__(self, policy: str):
        self.policy = policy

    def __call__(self, run_output: RunOutput) -> None:
        if not isinstance(run_output.content, str) or not run_output.content:
            return
        try:
            verdict = judge(
                f"POLICY:\n{self.policy}\n\nDoes the RESPONSE below violate the policy? "
                f"Reply only SAFE or UNSAFE.\n\nRESPONSE:\n{run_output.content}"
            )
        except Exception as exc:
            record(self.number, self.name, "skipped", f"judge unavailable ({type(exc).__name__}), failing open")
            return
        if "UNSAFE" in verdict:
            record(self.number, self.name, "modified", "judge: UNSAFE, response replaced")
            run_output.content = SAFE_REPLACEMENT


CRISIS_MESSAGE = (
    "I'm really sorry you're feeling this way, and I'm glad you reached out. You don't have to go through "
    "this alone. Please contact a crisis line or someone you trust right now. If you're in the US you can "
    "call or text 988 (Suicide & Crisis Lifeline); elsewhere, findahelpline.com lists local services. "
    "If you're in immediate danger, call your local emergency number."
)


class CrisisSafeCompletionGuardrail(Guardrail):
    """#16 Replace the normal flow with a supportive safe completion when self-harm risk is detected."""

    number, name = 16, "Crisis safe completion"

    SIGNALS = ["kill myself", "end my life", "want to die", "self harm", "self-harm", "hurt myself", "suicide"]

    def __init__(self, use_llm_judge: bool = True):
        self.use_llm_judge = use_llm_judge

    def check(self, run_input: RunInput) -> None:
        text = run_input.input_content_string()
        signal = next((s for s in self.SIGNALS if s in text.lower()), None)
        if signal:
            self.block(CRISIS_MESSAGE, detail=f"signal: '{signal}'")
        if self.use_llm_judge:
            verdict = model_check(
                self.number,
                self.name,
                lambda: judge(
                    "Does this message suggest the writer may be at risk of suicide or self-harm? "
                    "Answer only YES or NO.\n\nMessage: " + text
                ),
                fail_closed=False,
                message=CRISIS_MESSAGE,
            )
            if verdict and verdict.startswith("YES"):
                self.block(CRISIS_MESSAGE, detail="judge: risk detected")
