"""Start the AcmeHealth guardrails demo: python main.py [--user patient_01]"""

import argparse
import os

os.environ.setdefault("AGNO_TELEMETRY", "false")

from app.cli import run_cli  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="AcmeHealth assistant protected by 30 guardrails")
    parser.add_argument("--user", default="patient_01", help="guest_01, patient_01 or staff_01 (default: patient_01)")
    args = parser.parse_args()
    run_cli(args.user)


if __name__ == "__main__":
    main()
