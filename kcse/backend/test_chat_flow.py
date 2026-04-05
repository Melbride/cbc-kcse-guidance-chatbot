import argparse
import json
import sys
import time
from pathlib import Path

import requests


DEFAULT_API_BASE = "http://127.0.0.1:8000"

QUESTION_SETS = {
    "greetings": [
        "Hello",
        "Hi",
        "Hey",
        "Good morning",
    ],
    "smoke": [
        "Hello",
        "What can I study with my grades?",
        "computer science",
        "what are the requirements?",
        "I enjoy working with laptops",
        "teaching courses",
        "tell me about teaching",
        "diploma in teacher education",
        "artisan plumbing",
    ],
    "broad": [
        "What can I study with my grades?",
        "Which courses fit my KCSE results?",
        "I want career guidance based on my profile",
        "Based on my subjects, what degree courses can I pursue?",
        "Suggest courses for me",
    ],
    "fields": [
        "computer science",
        "engineering programmes",
        "teaching courses",
        "business studies",
        "nursing",
        "agriculture",
    ],
    "followups": [
        "computer science",
        "what are the requirements?",
        "what is computer science?",
        "what is computer science about?",
        "what can I do with computer science?",
        "yes",
        "tell me more",
    ],
    "descriptions": [
        "what is computer science about?",
        "what is computer science?",
        "tell me about civil engineering",
        "what do you learn in teaching?",
        "what can I do with actuarial science?",
        "what is nursing about?",
    ],
    "interests": [
        "I enjoy working with laptops",
        "I like technology",
        "I enjoy solving problems",
        "I like helping people",
        "I prefer hands-on work",
        "I enjoy business",
    ],
    "edge": [
        "?",
        "123",
        "xyz",
        "asdfgh",
        "help me choose",
        "I don't know what to study",
        "something related to art and design",
    ],
    "no_results": [
        "pilot training",
        "space science",
        "fashion design",
        "marine biology in kisumu",
        "music production",
    ],
    "random": [
        "Can you help me choose something I won't regret later?",
        "I am confused and I need guidance",
        "Which course fits someone who likes tech but also people?",
        "What if I want a course that leads to a job quickly?",
        "I got mixed grades, where do I even start?",
        "Can I still do something good if I do not want engineering?",
        "What course would suit me if I like computers but not too much theory?",
        "I want something practical but still marketable",
    ],
    "full": [
        "Hello",
        "What can I study with my grades?",
        "Which courses fit my KCSE results?",
        "I want career guidance based on my profile",
        "computer science",
        "what are the requirements?",
        "I enjoy working with laptops",
        "engineering programmes",
        "teaching courses",
        "tell me about teaching",
        "diploma in teacher education",
        "artisan plumbing",
        "animation courses",
        "what is computer science about?",
        "tell me about civil engineering",
        "what do you learn in teaching?",
        "business studies",
        "nursing",
        "agriculture",
        "pilot training",
    ],
    "full_user": [
        "Hello",
        "What can I study with my grades?",
        "Which courses fit my KCSE results?",
        "I want career guidance based on my profile",
        "Based on my subjects, what degree courses can I pursue?",
        "computer science",
        "what is computer science?",
        "what is computer science about?",
        "what are the requirements?",
        "what can I do with computer science?",
        "I enjoy working with laptops",
        "engineering programmes",
        "tell me about civil engineering",
        "teaching courses",
        "tell me about teaching",
        "diploma in teacher education",
        "business studies",
        "nursing",
        "agriculture",
        "animation courses",
        "artisan plumbing",
        "pilot training",
        "space science",
        "help me choose",
        "I don't know what to study",
        "?",
        "yes",
    ],
}

SAMPLE_PROFILE = {
    "name": "Test Student",
    "email": "test@example.com",
    "mean_grade": "B",
    "interests": "technology",
    "career_goals": "work in ICT",
    "subjects": [
        "Math:A",
        "Eng:B+",
        "Kis:B",
        "Bio:A-",
        "Chem:B-",
        "Geo:B-",
        "Hist:C+",
    ],
}

BAD_PHRASES = [
    "server error",
    "internal server error",
    "request failed",
    "traceback",
    "max retries exceeded",
]

ROBOTIC_PHRASES = [
    "well-recognized",
    "prestigious",
    "best university",
    "top-ranked",
    "affordable",
]

CONFUSING_PHRASES = [
    "current programme database",
]

SHORT_DIRECT_QUESTIONS = {
    "what is computer science?",
    "what is computer science about?",
    "what is nursing?",
    "what is nursing about?",
}


def fetch_profile(api_base: str, email: str) -> dict:
    response = requests.get(f"{api_base}/user/profile", params={"email": email}, timeout=30)
    response.raise_for_status()
    profile = response.json()
    extra_data = profile.get("extra_data", {})
    if isinstance(extra_data, str):
        try:
            extra_data = json.loads(extra_data)
        except Exception:
            extra_data = {}
    subjects = extra_data.get("subjects", profile.get("subjects", []))
    profile["subjects"] = subjects if isinstance(subjects, list) else []
    return profile


def load_questions(args) -> list[str]:
    questions = []
    if args.set_name:
        questions.extend(QUESTION_SETS[args.set_name])
    if args.question:
        questions.extend(args.question)
    if args.file:
        file_path = Path(args.file)
        for line in file_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped:
                questions.append(stripped)
    return questions


def print_block(title: str, text: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    print(text.strip() if text else "(empty)")


def looks_like_failure(answer_text: str) -> list[str]:
    findings = []
    lowered = answer_text.lower()
    for phrase in BAD_PHRASES:
        if phrase in lowered:
            findings.append(f"contains failure phrase: {phrase}")
    for phrase in ROBOTIC_PHRASES:
        if phrase in lowered:
            findings.append(f"contains restricted tone phrase: {phrase}")
    for phrase in CONFUSING_PHRASES:
        if phrase in lowered:
            findings.append(f"contains awkward system phrase: {phrase}")
    if len(answer_text.strip()) < 12:
        findings.append("answer is suspiciously short")
    return findings


def expected_signal(question: str) -> str:
    lowered = question.lower()
    if "requirements" in lowered:
        return "requirements"
    if "computer science" in lowered:
        return "computer science"
    if "teaching" in lowered:
        return "teaching"
    if "plumbing" in lowered:
        return "plumbing"
    if "animation" in lowered:
        return "animation"
    if "nursing" in lowered:
        return "nursing"
    if "engineering" in lowered:
        return "engineering"
    return ""


def is_no_result_query(question: str) -> bool:
    lowered = question.lower()
    return lowered in {item.lower() for item in QUESTION_SETS["no_results"]}


def is_direct_description(question: str) -> bool:
    return question.strip().lower() in SHORT_DIRECT_QUESTIONS


def count_words(text: str) -> int:
    return len([part for part in text.split() if part.strip()])


def run_checks(question: str, answer: str, status_code: int) -> tuple[str, list[str]]:
    findings = []
    if status_code != 200:
        findings.append(f"unexpected status code: {status_code}")

    findings.extend(looks_like_failure(answer))

    signal = expected_signal(question)
    if signal and signal not in answer.lower():
        findings.append(f"expected answer to mention: {signal}")

    if question.lower().strip() in {"hello", "hi", "hey", "good morning"}:
        lowered = answer.lower()
        greeting_tokens = [
            "hello",
            "hi",
            "i can help",
            "you can start",
            "explore courses",
        ]
        if not any(token in lowered for token in greeting_tokens):
            findings.append("greeting response did not look like a greeting")

    if is_no_result_query(question):
        lowered = answer.lower()
        allowed = [
            "no similar programmes found",
            "do not have",
            "general explanation",
            "i do not yet have",
            "could not find",
        ]
        if not any(token in lowered for token in allowed):
            findings.append("no-result query did not look safely handled")

    if is_direct_description(question) and count_words(answer) > 170:
        findings.append("direct description answer is too long")

    if question.lower().strip() == "yes" and "field" not in answer.lower() and "programme" not in answer.lower():
        findings.append("follow-up 'yes' did not guide the user clearly")

    status = "PASS" if not findings else "WARN"
    return status, findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Run many chat questions against the KCSE chatbot API.")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="API base URL, default: http://127.0.0.1:8000")
    parser.add_argument("--email", help="Fetch a real user profile by email before testing")
    parser.add_argument("--set-name", choices=sorted(QUESTION_SETS.keys()), default="smoke", help="Built-in question set to run")
    parser.add_argument("--list-sets", action="store_true", help="List built-in question sets and exit")
    parser.add_argument("--question", action="append", help="Add one extra question. Can be used multiple times.")
    parser.add_argument("--file", help="Path to a text file with one question per line")
    parser.add_argument("--pause-ms", type=int, default=0, help="Pause between questions in milliseconds")
    parser.add_argument("--save-json", help="Optional path to save raw results as JSON")
    parser.add_argument("--quiet", action="store_true", help="Only print summary and warnings")
    args = parser.parse_args()

    if args.list_sets:
        print("Available question sets:")
        for name, items in sorted(QUESTION_SETS.items()):
            print(f"- {name}: {len(items)} questions")
        return 0

    questions = load_questions(args)
    if not questions:
        print("No questions provided.", file=sys.stderr)
        return 1

    try:
        user_profile = fetch_profile(args.api_base, args.email) if args.email else dict(SAMPLE_PROFILE)
    except Exception as exc:
        print(f"Could not load profile: {exc}", file=sys.stderr)
        return 1

    conversation_id = f"test-chat-{int(time.time())}"
    history = []
    results = []
    summary = {"PASS": 0, "WARN": 0}

    if not args.quiet:
        print_block("Profile Used", json.dumps(user_profile, indent=2))

    for index, question in enumerate(questions, 1):
        payload = {
            "query": question,
            "user_profile": json.dumps(user_profile),
            "conversation_id": conversation_id,
            "history": history,
        }

        try:
            response = requests.post(f"{args.api_base}/search", json=payload, timeout=60)
            data = response.json()
        except Exception as exc:
            answer = f"Request failed: {exc}"
            status_code = 0
            data = {"detail": answer}
        else:
            status_code = response.status_code
            answer = data.get("message") or data.get("reranked") or data.get("detail") or "(no message)"
            if isinstance(answer, list):
                answer = "\n".join(str(item) for item in answer)

        status, findings = run_checks(question, str(answer), status_code)
        summary[status] += 1

        if not args.quiet or findings:
            print_block(f"Q{index}: {question} [{status}]", str(answer))
            if findings:
                print("Checks:")
                for finding in findings:
                    print(f"- {finding}")

        history.append({"role": "user", "text": question})
        history.append({"role": "bot", "text": str(answer)})
        results.append(
            {
                "question": question,
                "status": status,
                "findings": findings,
                "status_code": status_code,
                "response": data,
            }
        )

        if args.pause_ms > 0:
            time.sleep(args.pause_ms / 1000)

    print("\nSummary")
    print("-------")
    print(f"PASS: {summary['PASS']}")
    print(f"WARN: {summary['WARN']}")

    if args.save_json:
        Path(args.save_json).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nSaved raw results to {args.save_json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
