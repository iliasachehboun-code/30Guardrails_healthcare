"""#14 RAG grounding check and #30 answer relevance check (both LLM-judge based, fail open)."""

from typing import Iterable

from agno.run.agent import RunOutput

from app.events import record
from app.llm import judge


class GroundingCheck:
    """#14 When the answer was built from knowledge-base results, verify every claim is supported."""

    number, name = 14, "RAG grounding"

    def __init__(self, source_tools: Iterable[str]):
        self.source_tools = set(source_tools)

    def __call__(self, run_output: RunOutput) -> None:
        if not isinstance(run_output.content, str) or not run_output.content:
            return
        context = "\n".join(
            str(t.result) for t in (run_output.tools or []) if t.tool_name in self.source_tools and t.result
        )
        if not context:
            return
        try:
            verdict = judge(
                "You are a fact-checker. Given the CONTEXT, is every medical claim in the ANSWER supported by it? "
                "Ignore greetings, empathy, disclaimers and advice to see a doctor. "
                "Reply only GROUNDED or HALLUCINATED.\n\n"
                f"CONTEXT:\n{context}\n\nANSWER:\n{run_output.content}"
            )
        except Exception as exc:
            record(self.number, self.name, "skipped", f"judge unavailable ({type(exc).__name__}), failing open")
            return
        if "HALLUCINATED" in verdict:
            record(self.number, self.name, "modified", "judge: HALLUCINATED, answer replaced")
            run_output.content = (
                "I couldn't verify that answer against the AcmeHealth knowledge base, so I won't guess. "
                "Please ask a clinician or rephrase your question."
            )


class RelevanceCheck:
    """#30 Replace answers that do not address the user's question."""

    number, name = 30, "Answer relevance"

    def __call__(self, run_output: RunOutput) -> None:
        if not isinstance(run_output.content, str) or not run_output.content or run_output.input is None:
            return
        question = run_output.input.input_content_string()
        try:
            verdict = judge(
                "Does the ANSWER address the QUESTION (a polite refusal or a request for missing details also counts)? "
                "Reply only RELEVANT or IRRELEVANT.\n\n"
                f"QUESTION:\n{question}\n\nANSWER:\n{run_output.content}"
            )
        except Exception as exc:
            record(self.number, self.name, "skipped", f"judge unavailable ({type(exc).__name__}), failing open")
            return
        if "IRRELEVANT" in verdict:
            record(self.number, self.name, "modified", "judge: IRRELEVANT, answer replaced")
            run_output.content = "I'm not sure I answered your question. Could you rephrase or add more detail?"
