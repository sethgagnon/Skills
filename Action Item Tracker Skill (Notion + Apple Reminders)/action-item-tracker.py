#!/usr/bin/env python3
"""
Action Item Tracker
Extracts action items from recent Notion meetings and creates:
- ALL items in Notion Action Items database
- Selective Apple Reminders (only what Seth needs to act on)
"""

import os
import sys
import json
import re
import requests
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Set, Optional

# Configuration
NOTION_API_KEY = Path.home() / ".config" / "notion" / "api_key"
STATE_FILE = Path.home() / ".openclaw" / "workspace" / ".action-items-state.json"

# Notion database IDs
KNOWLEDGE_HUB_DATASOURCE = "NOTION_ID_REDACTED"
ACTION_ITEMS_DATASOURCE = "NOTION_ID_REDACTED"  # For querying
ACTION_ITEMS_DB = "NOTION_ID_REDACTED"  # For page creation
DAILY_NOTES_DATASOURCE = "NOTION_ID_REDACTED"

# Team configuration
DIRECT_REPORTS = {
    "Hunter", "Kory", "Matt", "Elizabeth", "Tim", 
    "Michael", "Sergio", "Dave", "Yanshen", "Chiku"
}

KNOWN_OWNERS = {
    "Seth", "Hunter", "Kory", "Matt", "Elizabeth", "Tim",
    "Michael", "Sergio", "Dave", "Yanshen", "Chiku",
    "Nick", "Stephen", "Ryan", "Sonnetta", "Greg", "Team"
}

# Action item keywords
ACTION_KEYWORDS = [
    "action items", "action item", "next steps", "follow up",
    "follow-up", "to do", "todo", "tasks", "deliverables"
]

class NotionClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Notion-Version": "2025-09-03"
        }
        self.headers_2022 = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
    
    def query_datasource(self, datasource_id: str, filter_obj: dict, sorts: list = None) -> dict:
        """Query a Notion datasource (uses 2025-09-03 API)"""
        url = f"https://api.notion.com/v1/data_sources/{datasource_id}/query"
        payload = {"filter": filter_obj}
        if sorts:
            payload["sorts"] = sorts
        
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()
    
    def get_blocks(self, page_id: str) -> List[dict]:
        """Get all blocks from a page"""
        url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        all_blocks = []
        
        while url:
            response = requests.get(url, headers=self.headers_2022)
            response.raise_for_status()
            data = response.json()
            all_blocks.extend(data.get("results", []))
            url = data.get("next_cursor")
            if url:
                url = f"https://api.notion.com/v1/blocks/{page_id}/children?start_cursor={url}"
            else:
                break
        
        return all_blocks
    
    def create_page(self, database_id: str, properties: dict) -> dict:
        """Create a new page in a database"""
        url = "https://api.notion.com/v1/pages"
        payload = {
            "parent": {"database_id": database_id},
            "properties": properties
        }
        
        response = requests.post(url, headers=self.headers_2022, json=payload)
        response.raise_for_status()
        return response.json()

def load_state() -> dict:
    """Load processed meetings state"""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"processedMeetings": [], "lastRun": ""}

def save_state(state: dict):
    """Save processed meetings state"""
    state["lastRun"] = datetime.now().isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def get_recent_meetings(notion: NotionClient, days: int = 7) -> List[dict]:
    """Get meetings from the past N days"""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    filter_obj = {
        "and": [
            {"property": "Type", "select": {"equals": "Meeting"}},
            {"property": "Date", "date": {"on_or_after": cutoff}}
        ]
    }
    
    sorts = [{"property": "Date", "direction": "descending"}]
    
    result = notion.query_datasource(KNOWLEDGE_HUB_DATASOURCE, filter_obj, sorts)
    return result.get("results", [])

def extract_text_from_block(block: dict) -> str:
    """Extract plain text from a Notion block"""
    block_type = block.get("type")
    if not block_type:
        return ""
    
    content = block.get(block_type, {})
    rich_text = content.get("rich_text", [])
    
    return " ".join([rt.get("plain_text", "") for rt in rich_text])

def parse_owner(text: str) -> Optional[str]:
    """Extract owner from action item text"""
    text_lower = text.lower()
    
    # Pattern: "Name - Action" or "Name to action" or "[Name] action"
    for owner in KNOWN_OWNERS:
        owner_lower = owner.lower()
        if (
            text_lower.startswith(f"{owner_lower} -") or
            text_lower.startswith(f"{owner_lower} to ") or
            text_lower.startswith(f"[{owner_lower}]") or
            f"{owner_lower}:" in text_lower
        ):
            return owner
    
    # Default to Seth if ambiguous
    return "Seth"

def parse_priority(text: str) -> str:
    """Determine priority from text"""
    text_lower = text.lower()
    if any(word in text_lower for word in ["urgent", "asap", "critical", "high priority"]):
        return "High"
    elif "low priority" in text_lower:
        return "Low"
    return "Medium"

def parse_due_date(text: str) -> Optional[str]:
    """Parse due date from text (simple heuristics)"""
    text_lower = text.lower()
    today = datetime.now()
    
    if "tomorrow" in text_lower or "asap" in text_lower:
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    elif "eow" in text_lower or "end of week" in text_lower or "friday" in text_lower:
        # Find next Friday
        days_ahead = 4 - today.weekday()  # Friday is 4
        if days_ahead <= 0:
            days_ahead += 7
        return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    elif "next week" in text_lower:
        return (today + timedelta(days=7)).strftime("%Y-%m-%d")
    elif "monday" in text_lower:
        days_ahead = 0 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    
    return None

def extract_action_items(notion: NotionClient, meeting: dict) -> List[dict]:
    """Extract action items from a meeting page."""
    page_id = meeting["id"]
    blocks = notion.get_blocks(page_id)

    action_items = []
    seen_normalized: Set[str] = set()
    in_action_section = False
    
    for block in blocks:
        block_type = block.get("type")
        text = extract_text_from_block(block)
        
        # Check if we're entering an action items section
        if block_type in ["heading_2", "heading_3"]:
            text_lower = text.lower()
            in_action_section = any(keyword in text_lower for keyword in ACTION_KEYWORDS)
            continue
        
        # Extract items from action section
        if in_action_section and block_type in ["bulleted_list_item", "numbered_list_item", "to_do"]:
            if text.strip() and not is_noise_task(text):
                normalized = normalize_task_text(text)
                if normalized in seen_normalized:
                    continue  # de-dup within the same meeting
                seen_normalized.add(normalized)

                owner = parse_owner(text)
                priority = parse_priority(text)
                due_date = parse_due_date(text)

                action_items.append({
                    "task": text.strip(),
                    "owner": owner,
                    "priority": priority,
                    "due_date": due_date,
                    "source_meeting_id": page_id,
                    "source_meeting_title": meeting.get("properties", {}).get("Name", {}).get("title", [{}])[0].get("plain_text", "Unknown Meeting")
                })
    
    return action_items

def get_existing_notion_items(notion: NotionClient) -> List[dict]:
    """Get existing action items from Notion (not Done)"""
    filter_obj = {
        "property": "Status",
        "select": {"does_not_equal": "Done"}
    }
    
    result = notion.query_datasource(ACTION_ITEMS_DATASOURCE, filter_obj)
    return result.get("results", [])

def get_existing_reminders(list_name: str) -> List[dict]:
    """Get existing reminders from Apple Reminders"""
    try:
        result = subprocess.run(
            ["remindctl", "list", list_name, "--json"],
            capture_output=True,
            text=True,
            check=True
        )
        return json.loads(result.stdout) if result.stdout.strip() else []
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return []

def normalize_task_text(text: str) -> str:
    """Normalize task text for reliable deduplication across formatting differences."""
    t = (text or "").strip()
    t = re.sub(r"^\[\s*\]\s*", "", t)  # markdown checkbox prefix
    t = re.sub(r"^\[[^\]]+\]\s*:?\s*", "", t)  # [Owner]: prefix
    t = re.sub(r"\*+", "", t)  # markdown bold/italic markers
    t = re.sub(r"\(Due:[^)]+\)", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\[(high|medium|low) priority\]", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t)
    return t.strip(" .;:-").lower()


def is_noise_task(text: str) -> bool:
    """Filter placeholders and non-action artifacts."""
    t = normalize_task_text(text)
    if not t:
        return True
    return t.startswith("none") or t.startswith("no action items")


def is_duplicate_text(new_text: str, existing_items: List[str]) -> bool:
    """Check if text is duplicate using normalized exact match + overlap heuristic."""
    normalized_new = normalize_task_text(new_text)
    if not normalized_new:
        return False

    normalized_existing = [normalize_task_text(x) for x in existing_items if x]
    if normalized_new in normalized_existing:
        return True

    new_words = set(normalized_new.split())
    if not new_words:
        return False

    for existing in normalized_existing:
        existing_words = set(existing.split())
        if not existing_words:
            continue
        overlap = len(new_words & existing_words) / len(new_words)
        if overlap > 0.8:
            return True

    return False

def should_create_reminder(item: dict) -> Optional[str]:
    """
    Determine if an Apple Reminder should be created, and which list.
    Returns: "Work" or "Work Follow Ups".

    Rule:
    - Seth-owned tasks -> Work
    - All non-Seth tasks -> Work Follow Ups
    """
    owner = item["owner"]

    if owner == "Seth":
        return "Work"

    return "Work Follow Ups"

def create_notion_action_item(notion: NotionClient, item: dict) -> str:
    """Create action item in Notion, return page ID"""
    properties = {
        "Task": {"title": [{"text": {"content": item["task"]}}]},
        "Owner": {"select": {"name": item["owner"]}},
        "Status": {"select": {"name": "To Do"}},
        "Priority": {"select": {"name": item["priority"]}},
        "Category": {"select": {"name": "Work"}}
    }
    
    if item["due_date"]:
        properties["Due Date"] = {"date": {"start": item["due_date"]}}
    
    if item.get("source_meeting_id"):
        properties["Source Meeting"] = {"relation": [{"id": item["source_meeting_id"]}]}
    
    page = notion.create_page(ACTION_ITEMS_DB, properties)
    return page["id"]

def create_apple_reminder(item: dict, list_name: str, notion_url: str):
    """Create Apple Reminder"""
    task_text = item["task"]
    if list_name == "Work Follow Ups" and item["owner"] != "Seth":
        task_text = f"Follow up: {item['task']} - {item['owner']}"
    
    cmd = ["remindctl", "add", task_text, "--list", list_name]
    
    if item["due_date"]:
        cmd.extend(["--due", item["due_date"]])
    
    notes = f"From: {item['source_meeting_title']}\n\nNotion: {notion_url}"
    cmd.extend(["--notes", notes])
    
    subprocess.run(cmd, check=True, capture_output=True)

def main():
    print("Starting Action Item Tracker...")
    
    # Load API key
    if not NOTION_API_KEY.exists():
        print("❌ Notion API key not found")
        sys.exit(1)
    
    api_key = NOTION_API_KEY.read_text().strip()
    notion = NotionClient(api_key)
    
    # Load state
    state = load_state()
    processed_ids = set(state.get("processedMeetings", []))
    print(f"Loaded {len(processed_ids)} processed meeting IDs")
    
    # Get recent meetings
    print("\n📬 Fetching recent meetings...")
    meetings = get_recent_meetings(notion, days=7)
    print(f"Found {len(meetings)} meetings from past 7 days")
    
    # Filter to new meetings only
    new_meetings = [m for m in meetings if m["id"] not in processed_ids]
    print(f"NEW meetings to process: {len(new_meetings)}")
    
    if not new_meetings:
        print("✅ No new meetings to process")
        return
    
    # Get existing items for deduplication
    print("\n🔍 Loading existing items for deduplication...")
    existing_notion = get_existing_notion_items(notion)
    existing_notion_titles = [
        item.get("properties", {}).get("Task", {}).get("title", [{}])[0].get("plain_text", "")
        for item in existing_notion
    ]

    existing_work_reminders = get_existing_reminders("Work")
    existing_work_titles = [r.get("title", "") for r in existing_work_reminders]

    existing_followup_reminders = get_existing_reminders("Work Follow Ups")
    existing_followup_titles = [r.get("title", "") for r in existing_followup_reminders]

    # Track normalized text so duplicates in THIS run are also blocked
    notion_seen_normalized = {normalize_task_text(t) for t in existing_notion_titles if t}
    work_seen_normalized = {normalize_task_text(t) for t in existing_work_titles if t}
    followup_seen_normalized = {normalize_task_text(t) for t in existing_followup_titles if t}
    
    print(f"Existing Notion items: {len(existing_notion_titles)}")
    print(f"Existing Work reminders: {len(existing_work_titles)}")
    print(f"Existing Follow-up reminders: {len(existing_followup_titles)}")
    
    # Process each new meeting
    all_action_items = []
    
    for meeting in new_meetings:
        meeting_title = meeting.get("properties", {}).get("Name", {}).get("title", [{}])[0].get("plain_text", "Unknown")
        print(f"\n📝 Processing: {meeting_title}")
        
        items = extract_action_items(notion, meeting)
        print(f"  Extracted {len(items)} action items")
        
        all_action_items.extend(items)
        processed_ids.add(meeting["id"])
    
    if not all_action_items:
        print("\n✅ No action items found in new meetings")
        save_state({"processedMeetings": list(processed_ids)})
        return
    
    # Create items
    print(f"\n✨ Creating {len(all_action_items)} action items...")
    
    stats = {
        "notion_created": 0,
        "work_created": 0,
        "followup_created": 0,
        "notion_only": 0,
        "duplicates_skipped": 0
    }
    
    created_items = []
    
    for item in all_action_items:
        normalized_task = normalize_task_text(item["task"])

        # Check for duplicates (Notion existing + current run)
        if normalized_task in notion_seen_normalized or is_duplicate_text(item["task"], existing_notion_titles):
            print(f"  ⏭️  Skipped duplicate: {item['task'][:60]}...")
            stats["duplicates_skipped"] += 1
            continue

        # Create in Notion
        try:
            page_id = create_notion_action_item(notion, item)
            notion_url = f"https://www.notion.so/{page_id.replace('-', '')}"
            stats["notion_created"] += 1
            notion_seen_normalized.add(normalized_task)
            
            # Determine if reminder needed
            reminder_list = should_create_reminder(item)
            
            if reminder_list == "Work":
                if normalized_task not in work_seen_normalized and not is_duplicate_text(item["task"], existing_work_titles):
                    create_apple_reminder(item, "Work", notion_url)
                    stats["work_created"] += 1
                    work_seen_normalized.add(normalized_task)
                    print(f"  ✅ Work: {item['task'][:60]}...")
                else:
                    print(f"  📋 Notion only (duplicate in Work): {item['task'][:60]}...")
                    stats["notion_only"] += 1

            elif reminder_list == "Work Follow Ups":
                if normalized_task not in followup_seen_normalized and not is_duplicate_text(item["task"], existing_followup_titles):
                    create_apple_reminder(item, "Work Follow Ups", notion_url)
                    stats["followup_created"] += 1
                    followup_seen_normalized.add(normalized_task)
                    print(f"  ✅ Follow-up: {item['task'][:60]}... ({item['owner']})")
                else:
                    print(f"  📋 Notion only (duplicate in Follow-ups): {item['task'][:60]}...")
                    stats["notion_only"] += 1
            
            else:
                stats["notion_only"] += 1
                print(f"  📋 Notion only ({item['owner']}, {item['priority']}): {item['task'][:60]}...")
            
            created_items.append({
                "task": item["task"],
                "owner": item["owner"],
                "priority": item["priority"],
                "due_date": item["due_date"],
                "notion_url": notion_url,
                "reminder_list": reminder_list
            })
        
        except Exception as e:
            print(f"  ❌ Error creating item: {e}")
    
    # Save state
    save_state({"processedMeetings": list(processed_ids)})
    
    # Print summary
    print("\n" + "="*60)
    print("📋 ACTION ITEM TRACKER - SUMMARY")
    print("="*60)
    print(f"\n✅ PROCESSING COMPLETE\n")
    print(f"MEETINGS ANALYZED (Past 7 days):")
    print(f"• Total meetings found: {len(meetings)}")
    print(f"• Already processed (SKIPPED): {len(meetings) - len(new_meetings)}")
    print(f"• NEW meetings processed: {len(new_meetings)}")
    
    if new_meetings:
        print(f"\nNEW MEETINGS:")
        for i, m in enumerate(new_meetings, 1):
            title = m.get("properties", {}).get("Name", {}).get("title", [{}])[0].get("plain_text", "Unknown")
            print(f"{i}. ✓ {title}")
    
    print(f"\nACTION ITEMS CREATED:")
    print(f"Total new action items extracted and created: {stats['notion_created']}")
    
    print(f"\nIn Notion Action Items Database: {stats['notion_created']}")
    work_items = [item for item in created_items if item["reminder_list"] == "Work"]
    for i, item in enumerate(work_items, 1):
        due_str = f", Due: {item['due_date']}" if item['due_date'] else ""
        print(f"{i}. ✓ {item['task'][:80]}{due_str}")
    
    print(f"\nIn Apple Reminders (Work list): {stats['work_created']}")
    print(f"In Apple Reminders (Work Follow Ups list): {stats['followup_created']}")
    print(f"Notion only (no reminder): {stats['notion_only']}")
    
    if stats['duplicates_skipped'] > 0:
        print(f"\nDEDUPLICATION:")
        print(f"• Skipped {stats['duplicates_skipped']} duplicate(s)")
    
    print(f"\nSTATE FILE:")
    print(f"✓ Updated .action-items-state.json")
    print(f"✓ Total meetings tracked: {len(processed_ids)}")

if __name__ == "__main__":
    main()
