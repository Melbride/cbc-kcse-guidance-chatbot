import json
import os
from datetime import datetime, timezone
from uuid import uuid4

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
ANNOUNCEMENTS_FILE = os.path.join(DATA_DIR, "admin_announcements.json")
SUPPORT_CONTENT_FILE = os.path.join(DATA_DIR, "admin_support_content.json")
QUESTION_LOGS_FILE = os.path.join(DATA_DIR, "admin_question_logs.json")

def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

def _read_json_list(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as file_handle:
        try:
            data = json.load(file_handle)
        except json.JSONDecodeError:
            return []
    return data if isinstance(data, list) else []

def _write_json_list(path, data):
    _ensure_data_dir()
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump(data, file_handle, indent=2)

def list_announcements():
    announcements = _read_json_list(ANNOUNCEMENTS_FILE)
    return sorted(announcements, key=lambda item: item.get("created_at", ""), reverse=True)

def create_announcement(title: str, message: str, created_by: str):
    announcements = _read_json_list(ANNOUNCEMENTS_FILE)
    announcement = {
        "id": str(uuid4()),
        "title": title,
        "message": message,
        "created_by": created_by,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    announcements.append(announcement)
    _write_json_list(ANNOUNCEMENTS_FILE, announcements)
    return announcement

def list_support_content():
    items = _read_json_list(SUPPORT_CONTENT_FILE)
    return sorted(items, key=lambda item: item.get("updated_at", item.get("created_at", "")), reverse=True)

def create_support_content(title: str, category: str, content: str, status: str, created_by: str):
    items = _read_json_list(SUPPORT_CONTENT_FILE)
    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "id": str(uuid4()),
        "title": title,
        "category": category,
        "content": content,
        "status": status,
        "created_by": created_by,
        "created_at": now,
        "updated_at": now
    }
    items.append(entry)
    _write_json_list(SUPPORT_CONTENT_FILE, items)
    return entry

def delete_support_content(item_id: str):
    items = _read_json_list(SUPPORT_CONTENT_FILE)
    remaining = [item for item in items if item.get("id") != item_id]
    if len(remaining) == len(items):
        return False
    _write_json_list(SUPPORT_CONTENT_FILE, remaining)
    return True

def update_support_content(item_id: str, title: str, category: str, content: str, status: str):
    items = _read_json_list(SUPPORT_CONTENT_FILE)
    updated = None
    for item in items:
        if item.get("id") == item_id:
            item["title"] = title
            item["category"] = category
            item["content"] = content
            item["status"] = status
            item["updated_at"] = datetime.now(timezone.utc).isoformat()
            updated = item
            break

    if not updated:
        return None

    _write_json_list(SUPPORT_CONTENT_FILE, items)
    return updated

def create_question_log(conversation_id: str, question: str, response: str, status: str, topic: str = "General"):
    logs = _read_json_list(QUESTION_LOGS_FILE)
    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "id": str(uuid4()),
        "conversation_id": conversation_id,
        "question": question,
        "response": response,
        "status": status,
        "topic": topic or "General",
        "reviewed": False,
        "review_note": "",
        "created_at": now,
        "updated_at": now
    }
    logs.append(entry)
    _write_json_list(QUESTION_LOGS_FILE, logs)
    return entry

def list_question_logs(status: str | None = None, topic: str | None = None, date_from: str | None = None):
    logs = _read_json_list(QUESTION_LOGS_FILE)

    if status:
        logs = [item for item in logs if str(item.get("status", "")).lower() == status.lower()]
    if topic:
        logs = [item for item in logs if topic.lower() in str(item.get("topic", "")).lower()]
    if date_from:
        logs = [item for item in logs if str(item.get("created_at", ""))[:10] >= date_from]

    return sorted(logs, key=lambda item: item.get("created_at", ""), reverse=True)

def summarize_question_logs(limit: int = 10, status: str | None = None, topic: str | None = None, date_from: str | None = None):
    logs = list_question_logs(status=status, topic=topic, date_from=date_from)
    counts = {}
    for item in logs:
        question = str(item.get("question", "")).strip().lower()
        if not question:
            continue
        counts[question] = counts.get(question, 0) + 1

    return [
        {"question": question, "count": count}
        for question, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:limit]
    ]

def question_status_summary(topic: str | None = None, date_from: str | None = None):
    logs = list_question_logs(topic=topic, date_from=date_from)
    summary = {}
    for item in logs:
        status = str(item.get("status", "unknown")).lower()
        summary[status] = summary.get(status, 0) + 1
    return summary

def update_question_review(item_id: str, reviewed: bool, review_note: str = ""):
    logs = _read_json_list(QUESTION_LOGS_FILE)
    updated = None
    for item in logs:
        if item.get("id") == item_id:
            item["reviewed"] = reviewed
            item["review_note"] = review_note
            item["updated_at"] = datetime.now(timezone.utc).isoformat()
            updated = item
            break

    if not updated:
        return None

    _write_json_list(QUESTION_LOGS_FILE, logs)
    return updated
