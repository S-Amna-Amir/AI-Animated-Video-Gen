"""
main.py
-------
Project Montage — Entry Point.

Usage:
    python main.py                              # interactive mode
    python main.py --phase 1 --mode auto --prompt "A spy thriller in Tokyo"
    python main.py --phase 1 --mode manual --file my_script.txt

Environment:
    Copy .env.example to .env and fill in GROQ_API_KEY (and optionally
    OPENAI_API_KEY) before running.
"""

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Logging ────────────────────────────────────────────────────────────────────
from shared.constants import OUTPUTS_DIR

OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(OUTPUTS_DIR / "run.log"), mode="a"),
    ],
)
logger = logging.getLogger(__name__)


# ── Input collection ───────────────────────────────────────────────────────────

def collect_interactive() -> dict:
    print("\n" + "═" * 60)
    print("  PROJECT MONTAGE — Phase 1: The Writer's Room")
    print("═" * 60)
    print("  Mode 1 (manual) : Upload your own screenplay")
    print("  Mode 2 (auto)   : Generate from a prompt\n")

    while True:
        mode = input("  Select mode [manual/auto]: ").strip().lower()
        if mode in ("manual", "auto"):
            break
        print("  Please enter 'manual' or 'auto'.")

    if mode == "manual":
        print("\n  Paste screenplay below. Enter 'END' on a blank line to finish:\n")
        lines = []
        while True:
            line = input()
            if line.strip().upper() == "END":
                break
            lines.append(line)
        raw_input = "\n".join(lines)
    else:
        raw_input = input("\n  Enter your story prompt:\n  > ").strip()

    return {"mode": mode, "raw_input": raw_input}


def collect_from_args(args: argparse.Namespace) -> dict:
    mode = args.mode.strip().lower()
    if mode == "manual":
        if args.file:
            fp = Path(args.file)
            if not fp.exists():
                logger.error(f"File not found: {fp}")
                sys.exit(1)
            raw_input = fp.read_text(encoding="utf-8")
        elif args.prompt:
            raw_input = args.prompt
        else:
            logger.error("Manual mode requires --file or --prompt.")
            sys.exit(1)
    else:
        if not args.prompt:
            logger.error("Auto mode requires --prompt.")
            sys.exit(1)
        raw_input = args.prompt
    return {"mode": mode, "raw_input": raw_input}


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Project Montage — AI Video Generation Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py
  python main.py --phase 1 --mode auto --prompt "A heist thriller in 1920s Paris"
  python main.py --phase 1 --mode manual --file my_script.txt
        """,
    )
    parser.add_argument("--phase",  type=int, choices=[1, 2, 3, 4, 5], default=1)
    parser.add_argument("--mode",   choices=["manual", "auto"])
    parser.add_argument("--prompt", type=str)
    parser.add_argument("--file",   type=str)
    args = parser.parse_args()

    # ── Phase routing ──────────────────────────────────────────────────────
    if args.phase == 1:
        from agents.orchestrator.workflow import run_phase1, print_summary

        if args.mode:
            collected = collect_from_args(args)
        else:
            collected = collect_interactive()

        try:
            final_state = run_phase1(
                mode=collected["mode"],
                raw_input=collected["raw_input"],
            )
        except Exception as e:
            logger.exception(f"Phase 1 crashed: {e}")
            sys.exit(1)

        print_summary(final_state)

        if final_state.get("status") not in ("complete", "processing"):
            print(f"\n[!] Pipeline ended with status: {final_state.get('status')}")
            if final_state.get("error_message"):
                print(f"    {final_state['error_message']}")
            if final_state.get("validation_errors"):
                for err in final_state["validation_errors"]:
                    print(f"      • {err}")
            sys.exit(1)

    else:
        print(f"Phase {args.phase} not yet implemented. Run --phase 1 to start.")
        sys.exit(0)


if __name__ == "__main__":
    main()
