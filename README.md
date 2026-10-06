# 30 Guardrails for AI & LLM Agents

<p align="center">
  <img src="assets/banner.png" width="100%" alt="30 Guardrails for AI and LLM Agents with Agno" />
</p>

A hands-on study project where I learned and explored how to make Large Language Model (LLM) agents safe, private, and production-ready using **guardrails**. The repository contains a runnable **local application**: an **AcmeHealth assistant** built with the **Agno SDK** on the **OpenAI API**, protected by **30 guardrails** and driven from an interactive terminal chat. A companion Jupyter notebook teaches every guardrail step by step.

---

## What This Project Covers

A guardrail is any layer of logic that inspects, modifies, or blocks what flows through an LLM agent. In Agno, guardrails are implemented as **hooks** attached to an `Agent`, running at well-defined checkpoints in the run lifecycle. This project explores all of them.

```
            USER INPUT
                |
   [pre_hooks]       ->  rate limit, length, invisible text, gibberish, language, crisis,
                |        injection, secrets, PII, keywords, URLs, prompt-attack, topic, moderation
            LLM CALL      (tool_call_limit + max_output_tokens cap the agent loop)
                |
   [tool_hooks]      ->  RBAC, tool-argument validation, indirect-injection scan
   [requires_confirmation] -> human approval in the terminal
                |
            TOOL RUNS     (triage tool returns a validated Pydantic schema)
                |
   [post_hooks]      ->  PII / secret / URL redaction, dangerous code, toxicity, leak,
                |        brand, moderation, safety judge, grounding, relevance, disclaimer
           USER RESPONSE ->  verdict + every guardrail decision logged to SQLite
```

Pre- and post-hooks run in the order they are listed and the first one that raises stops the run, so the ordering of guardrails is itself a security decision: cheap deterministic checks run first, paid model-based checks last, and output is redacted before it is judged.

---

## Guardrails Implemented

| # | Guardrail | Type | Where it runs |
|---|-----------|------|---------------|
| 1 | Keyword content filter | Deterministic | `pre_hooks` · `input_filters.py` |
| 2 | Prompt-injection / jailbreak detection | Deterministic | `pre_hooks` · `injection.py` |
| 3 | Topical / off-topic relevance | Model-based | `pre_hooks` · `topical.py` |
| 4 | Input length / cost limit | Deterministic | `pre_hooks` · `input_filters.py` |
| 5 | Built-in PII masking | Deterministic | `PIIDetectionGuardrail` · `pii.py` |
| 6 | Custom regex PII (insurance no., medical record no.) | Deterministic | `PIIDetectionGuardrail` · `pii.py` |
| 7 | OpenAI moderation (input + output, fails closed) | Model-based | `OpenAIModerationGuardrail` + `post_hooks` · `safety.py` |
| 8 | Tool-call limit and token cap | Deterministic | `tool_call_limit` / `max_output_tokens` |
| 9 | System-prompt-leak protection | Deterministic | `post_hooks` · `output_filters.py` |
| 10 | Human-in-the-loop approval | Process | `@tool(requires_confirmation=True)` + CLI prompt |
| 11 | Tool-argument validation (read-only SQL, valid bookings) | Deterministic | `tool_hooks` · `tool_guards.py` |
| 12 | Domain output-safety judge | Model-based | `post_hooks` · `safety.py` |
| 13 | Structured-output schema validation | Deterministic | `output_schema` · triage tool |
| 14 | RAG grounding / hallucination check | Model-based | `post_hooks` · `quality.py` |
| 15 | Brand-safety / competitor filter | Deterministic | `post_hooks` · `output_filters.py` |
| 16 | Self-harm / crisis safe-completion | Deterministic + Model-based | `pre_hooks` · `safety.py` |
| 17 | Observability / audit log of guardrail decisions | Utility | runner · `observability.py` (SQLite) |
| 18 | Prompt-attack classifier | Model-based | `pre_hooks` · `injection.py` |
| 19 | Invisible text / Unicode smuggling | Deterministic | `pre_hooks` · `input_filters.py` |
| 20 | Secrets / credential detection (input + output) | Deterministic | `pre_hooks` + `post_hooks` · `credentials.py` |
| 21 | Language restriction | Deterministic | `pre_hooks` · `input_filters.py` |
| 22 | Gibberish / nonsense detection | Deterministic | `pre_hooks` · `input_filters.py` |
| 23 | URL / domain allowlist (input + output) | Deterministic | `pre_hooks` + `post_hooks` · `urls.py` |
| 24 | Tool permissions / RBAC | Deterministic | `tool_hooks` · `tool_guards.py` |
| 25 | Indirect prompt injection in tool results | Deterministic | `tool_hooks` · `tool_guards.py` |
| 26 | Per-user rate limiting | Deterministic | `pre_hooks` · `input_filters.py` |
| 27 | Output PII redaction | Deterministic | `post_hooks` · `pii.py` |
| 28 | Dangerous code / command filter | Deterministic | `post_hooks` · `output_filters.py` |
| 29 | Toxicity / profanity filter | Deterministic | `post_hooks` · `output_filters.py` |
| 30 | Answer relevance check | Model-based | `post_hooks` · `quality.py` |

Guardrails 18–30 are inspired by public tools and standards: Meta Purple Llama (Prompt Guard, LlamaFirewall, Code Shield), LLM Guard by Protect AI (InvisibleText, Secrets, Language, Gibberish, MaliciousURLs, Sensitive, BanCode, Toxicity, Relevance), OpenAI Guardrails (URL filter), Guardrails AI (ProfanityFree) and the OWASP Top 10 for LLM Applications (LLM01, LLM02, LLM06, LLM10).

All 30 guardrails are wired into a single **AcmeHealth assistant** in `app/agents/healthcare.py`, with three demo users (guest, patient, staff) so you can watch role-based permissions, human approval and output redaction in action.

---

## Project Structure

```
30_Guardrails/
├── main.py                       # entry point: python main.py [--user patient_01]
├── requirements.txt
├── .env.example                  # copy to .env and add your OpenAI key
├── TESTING.md                    # manual test prompts for every guardrail
├── app/
│   ├── config.py                 # loads .env, model names, data paths
│   ├── llm.py                    # OpenAI model factories, LLM judge, moderation helper
│   ├── events.py                 # per-turn record of guardrail decisions
│   ├── runner.py                 # runs a turn, computes the verdict, handles approvals, writes the audit log
│   ├── cli.py                    # interactive terminal chat (rich)
│   ├── agents/
│   │   └── healthcare.py         # the agent: settings, roles, and the ordered 30-guardrail stack
│   ├── tools/
│   │   └── healthcare.py         # knowledge base, triage, booking, records, lab config, web articles
│   └── guardrails/
│       ├── base.py               # Guardrail base class + fail-open / fail-closed helper
│       ├── input_filters.py      # 1, 4, 19, 21, 22, 26
│       ├── injection.py          # 2, 18
│       ├── topical.py            # 3
│       ├── pii.py                # 5, 6, 27
│       ├── safety.py             # 7, 12, 16
│       ├── credentials.py        # 20
│       ├── urls.py               # 23
│       ├── output_filters.py     # 9, 15, 28, 29 + medical disclaimer
│       ├── quality.py            # 14, 30
│       ├── tool_guards.py        # 11, 24, 25
│       └── observability.py      # 17 (SQLite audit log)
├── notebooks/
│   └── guardrails_groq_agno_zero_to_production.ipynb   # step-by-step tutorial (Groq, Colab-friendly)
└── data/                         # created at runtime: agno.db (sessions, paused runs), guardrail_log.db
```

---

## Tech Stack

- **Agno** (`agno`) — agent framework: `Agent`, `BaseGuardrail`, pre/post/tool hooks, human-in-the-loop, `SqliteDb`
- **OpenAI API** (`openai`) — main model, cheap judge model and the Moderation API
- **Pydantic** — structured-output schema validation
- **SQLite** — conversation sessions, paused approvals and the guardrail audit log
- **langdetect** — deterministic language detection
- **rich** — terminal UI
- **Python 3.10+**

Models used by the app (override them in `.env`):

| Role | Model |
|------|-------|
| Main agent and triage classifier | `gpt-6.1-sol` |
| Cheap judge for model-based guardrails | `gpt-6-luna` |
| Input and output moderation | `omni-moderation-latest` |

Model identifiers can change over time. If one stops working, check the current
list in the OpenAI documentation and update `MAIN_MODEL` / `JUDGE_MODEL` in `.env`.

---

## Getting Started

### Prerequisites

- Python 3.10 or newer
- An OpenAI API key

### Installation

```bash
git clone https://github.com/<your-username>/30-Guardrails-for-AI-and-LLM-Agents.git
cd 30-Guardrails-for-AI-and-LLM-Agents

python -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### Configuration

Copy the example environment file and add your key:

```bash
cp .env.example .env             # on Windows: copy .env.example .env
```

```
OPENAI_API_KEY=sk-...
```

The key in `.env` takes priority over any `OPENAI_API_KEY` already set in your system environment.

### Run the demo

```bash
python main.py                   # starts as patient_01
python main.py --user staff_01   # or guest_01
```

Every answer shows a verdict (**ALLOWED**, **BLOCKED**, **PAUSED** or **ERROR**) and a table of the guardrails that acted on that turn. Booking an appointment pauses the agent and asks you to approve or reject the call in the terminal.

| Command | What it does |
|---------|--------------|
| `/user <id>` | switch between `guest_01`, `patient_01`, `staff_01` (unknown ids are guests) |
| `/whoami` | current user, role and session |
| `/new` | start a fresh conversation |
| `/guardrails` | list the 30 guardrails and where they run |
| `/log [n]` | last n turns from the SQLite audit log |
| `/stats` | verdict mix and guardrail firing counts |
| `/quit` | exit |

To switch a guardrail off or tune it, edit the `pre_hooks`, `tool_hooks` and `post_hooks` lists (and the settings above them) in `app/agents/healthcare.py`.

### Testing

[TESTING.md](TESTING.md) lists a ready-to-paste prompt for each of the 30 guardrails, which user to run it as, and the expected result.

### The notebook

`notebooks/guardrails_groq_agno_zero_to_production.ipynb` builds every guardrail one at a time with explanations. It uses the Groq API, so it can run standalone in Jupyter or Google Colab with a `GROQ_API_KEY`.

---

## What I Learned

- A guardrail is simply a hook running at a checkpoint that can inspect, modify, or block traffic. Once that idea is clear, every guardrail follows the same pattern.
- Deterministic guardrails (rules, regex, length checks) and model-based guardrails (LLM judges, classifiers) are complementary. Cheap deterministic checks should run first so you only pay for an LLM judge on inputs that survive.
- PII must be masked before anything is logged or sent to a third-party model, and redacted again on the way out, because tools and databases can leak it back.
- Agno only stops a run on `InputCheckError` / `OutputCheckError`; any other exception in a hook is logged and the run continues. Safety-critical model-based checks must convert their own failures into a check error (fail closed).
- High-impact and irreversible tool calls should require human approval, while lower-risk actions can be validated deterministically on their arguments. Permissions must be enforced in code (RBAC), never left to the model.
- Tool results are untrusted input: web pages and documents can carry indirect prompt injections.
- Output should never be trusted blindly. A final output guardrail (safety, grounding, relevance, schema) is essential.
- Loop, token and rate limits prevent runaway agents and denial-of-wallet abuse.
- Guardrails are never finished. They need observability, measurement, and continuous iteration as new attack patterns appear.

---

## Production Checklist

A summary of the practices explored in this project for shipping guarded agents:

1. Layer deterministic checks before model-based ones to fail fast and control cost.
2. Mask PII before any logging or third-party call, and redact it again in the output.
3. Always include a final output guardrail.
4. Require human approval for irreversible, high-impact tool calls, and enforce tool permissions in code.
5. Cap tool calls, tokens and per-user request rates to prevent runaway loops.
6. Scan tool results for indirect prompt injection.
7. Make safety-critical model-based checks fail closed.
8. Log every guardrail decision and review the firing rate.
9. Use a persistent database (Postgres, Redis, SQLite) rather than `InMemoryDb` in production.
10. Keep a labeled test set and re-run it after every guardrail change; tune thresholds carefully — too strict frustrates users, too loose is unsafe.

---

## Related Industry Tools

- **Agno built-in guardrails** — `PIIDetectionGuardrail`, `PromptInjectionGuardrail`, `OpenAIModerationGuardrail` (used in this project).
- **OpenAI Moderation API** — `omni-moderation-latest` (used in this project).
- **GPT-OSS-Safeguard** and **Llama Prompt Guard 2** — dedicated safety classifiers (used in the notebook via Groq).
- **Llama Guard / LlamaFirewall** — Meta Purple Llama safety models and agent firewall.
- **LLM Guard** — Protect AI's input/output scanner library.
- **NeMo Guardrails** — guardrail framework from NVIDIA.
- **Guardrails AI** — validation and output-schema library.
- **OWASP Top 10 for LLM Applications** — the threat model behind most of these guardrails.

---

## Disclaimer

This repository is an educational study project. The healthcare data, patient records and credentials in the tools are fake and exist only so the guardrails have something to catch. The crisis-detection guardrail is intentionally simplified to teach the pattern; a real product should use a trained classifier and be reviewed with qualified professionals. Always validate and adapt guardrails to your own domain, risk profile, and compliance requirements before deploying to production.

---

## Author

**Your Name**
- LinkedIn: [Iliass Achehboun](https://www.linkedin.com/in/your-linkedin/)
- GitHub: [iliasachehboun-code](https://github.com/your-github)


---
