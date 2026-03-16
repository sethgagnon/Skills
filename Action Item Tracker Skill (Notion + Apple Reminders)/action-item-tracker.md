# Action Item Tracker Skill (Notion + Apple Reminders)

**Triggers:** "check my action items", "extract action items", "review action items from meetings", automatic via cron

## Overview

Searches recent meetings in Notion Knowledge Hub, extracts action items, and creates entries in **both**:
1. **Notion Action Items database** - ALL action items for tracking/visibility
2. **Apple Reminders** - ONLY items Seth needs device notifications for:
   - **Owner = Seth** → "Work" list
   - **Owner ≠ Seth + needs follow-up** → "Work Follow Ups" list
   - **Owner ≠ Seth + no follow-up needed** → Notion only (no reminder)

Deduplicates against existing items in both systems.

**Key principle:** Not every action item needs a phone reminder. Notion tracks everything; Apple Reminders only get what Seth personally needs to act on or follow up on.

## Notion Configuration

**Important:** Notion API has two types of IDs:
- **Data Source ID** - Use with API version `2025-09-03` for querying
- **Database ID** - Use with API version `2022-06-28` for page creation

**Knowledge Hub:**
- Data Source ID: `NOTION_ID_REDACTED`
- Database ID: `NOTION_ID_REDACTED`
- Filter: Type = "Meeting" for meeting notes

**Action Items:**
- Data Source ID: `NOTION_ID_REDACTED`
- Database ID: `NOTION_ID_REDACTED`
- Properties:
  - Task (title)
  - Owner (select): Seth, Hunter, Kory, Matt, Elizabeth, Tim, Michael, Sergio, Dave, Yanshen, Chiku, Nick, Stephen, Ryan, Sonnetta, Greg, Team
  - Status (select): To Do, In Progress, Done, Blocked, Not Started
  - Priority (select): High, Medium, Low
  - Category (select): Follow-up, Decision Needed, Deliverable, Communication, Research, Work
  - Due Date (date)
  - Source Meeting (relation)

## Step 1: Query Recent Meetings

Get meetings from the past 7-14 days (use Data Source ID + API 2025-09-03):

```bash
NOTION_KEY=$(cat ~/.config/notion/api_key  # create this file locally with your key)

curl -s -X POST "https://api.notion.com/v1/data_sources/NOTION_ID_REDACTED/query" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{
    "filter": {
      "and": [
        {"property": "Type", "select": {"equals": "Meeting"}},
        {"property": "Date", "date": {"past_week": {}}}
      ]
    },
    "sorts": [{"property": "Date", "direction": "descending"}],
    "page_size": 30
  }'
```

## Step 2: Fetch Meeting Content

For each meeting, get the page blocks (use API 2022-06-28 for blocks):

```bash
curl -s "https://api.notion.com/v1/blocks/{meeting_page_id}/children?page_size=100" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2022-06-28"
```

Look for:
- Headings containing: "Action Items", "Next Steps", "Follow Up", "To Do"
- To-do blocks
- Bulleted/numbered lists after action item headings

## Step 3: Extract Action Items

Parse action items from content. Common patterns:

**Explicit assignments:**
- `Seth - Review the proposal` → Owner: Seth
- `Elizabeth to schedule meeting` → Owner: Elizabeth
- `[Team] Add questions to agenda` → Owner: Team

**For each extracted item, determine:**

| Field | Logic |
|-------|-------|
| Task | The action description |
| Owner | Match name against known owners; **do NOT default to Seth**. If ambiguous, set to "Team" (or "Unassigned" if available). |
| Priority | "urgent"/"ASAP" → High; default → Medium |
| Category | "follow up" → Follow-up; "decide" → Decision Needed; default → Work |
| Due Date | Parse from text (ASAP → Tomorrow, EOW → Friday, etc.) |
| Status | "To Do" for new items |
| Apple Reminder? | Apply Step 6 routing logic (see below) |

### Seth Assignment Guardrails (STRICT)

Only assign an item to **Seth** if at least one of these is true:
- Explicit owner mention: "Seth", "@Seth", "Seth to ..."
- Clear second-person imperative directed to Seth in a Seth-only context ("you need to ...")

If ownership is ambiguous:
- Set owner to **Team** (or **Unassigned**)
- Do **not** assign to Seth

Skip creating a Seth action item when text is only informational, such as:
- "Seth mentioned..."
- "Seth asked..."
- "Discussion about..."
- "FYI / update / status"

Minimum signal for Seth task creation:
- Explicit Seth ownership **and** an actionable verb (review/send/schedule/draft/decide/follow up)
- If missing due date + urgency + dependency, prefer Notion context note over task creation

### Hard Filters (before creating any task)

Do **not** create an action item when text is:
- Pure status update ("in progress", "ongoing", "reviewed status")
- Meeting meta/admin notes ("schedule next meeting", "send notes") unless explicitly assigned and meaningful
- Generic team intent without clear owner + concrete output

Create action items only for concrete, attributable, and trackable work.

**Practical examples:**

| Extracted Item | Owner | Priority | Apple Reminder? | Reasoning |
|----------------|-------|----------|-----------------|-----------|
| "Seth to review proposal by Friday" | Seth | High | ✅ Work | Owner = Seth |
| "Hunter to update documentation by EOW" | Hunter | Medium | ✅ Work Follow Ups | Direct report + near deadline |
| "Elizabeth researching vendor options (no rush)" | Elizabeth | Low | ❌ Notion only | Direct report but low priority |
| "Nick will handle budget approval" | Nick | High | ❌ Notion only | Not Seth's task, not a direct report |
| "Team to add agenda items" | Team | Low | ❌ Notion only | Informational, no individual owner |
| "Kory to deliver API keys for Seth's demo Friday" | Kory | High | ✅ Work Follow Ups | Blocks Seth's work + near deadline |

## Step 4: Check for Duplicates

Check **both** state file, Notion, and Apple Reminders for existing items.

### Load State File

Track which meetings have been processed:

```bash
STATE_FILE="$HOME/.openclaw/workspace/.state/action-items-state.json"

# Load or initialize state
if [[ -f "$STATE_FILE" ]]; then
  PROCESSED_MEETINGS=$(jq -r '.processedMeetings[]' "$STATE_FILE" 2>/dev/null)
else
  echo '{"processedMeetings":[],"lastRun":""}' > "$STATE_FILE"
  PROCESSED_MEETINGS=""
fi
```

**Skip meeting if:** Meeting ID is in processedMeetings list.

### Check Notion Action Items (use Data Source ID):

For new meetings, check if similar items already exist:

```bash
curl -s -X POST "https://api.notion.com/v1/data_sources/NOTION_ID_REDACTED/query" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{
    "filter": {
      "property": "Status", 
      "select": {"does_not_equal": "Done"}
    }
  }'
```

### Check Apple Reminders:

```bash
remindctl list "Work" --json > /tmp/work_reminders.json
remindctl list "Work Follow Ups" --json > /tmp/followup_reminders.json
```

### Fuzzy Match Logic

**Skip if:** Existing item matches >70% of words in new item title (case-insensitive).

```python
def is_duplicate(new_title, existing_items):
    """Check if new_title is similar to any existing item"""
    new_words = set(new_title.lower().split())
    
    for item in existing_items:
        existing_title = item.get('title', '')
        existing_words = set(existing_title.lower().split())
        
        # Calculate word overlap
        if len(new_words) > 0:
            overlap = len(new_words & existing_words) / len(new_words)
            if overlap > 0.7:  # 70% match threshold
                return True
    
    return False
```

## Step 5: Create Action Items in Notion

For each new item, create in Action Items database (use Database ID + API 2022-06-28):

```bash
curl -s -X POST "https://api.notion.com/v1/pages" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d '{
    "parent": {"database_id": "NOTION_ID_REDACTED"},
    "properties": {
      "Task": {"title": [{"text": {"content": "Review AgentCore proposal with Steve"}}]},
      "Owner": {"select": {"name": "Seth"}},
      "Status": {"select": {"name": "To Do"}},
      "Priority": {"select": {"name": "Medium"}},
      "Category": {"select": {"name": "Work"}},
      "Due Date": {"date": {"start": "2026-01-31"}},
      "Source Meeting": {"relation": [{"id": "meeting_page_id"}]}
    }
  }'
```

## Step 6: Create Apple Reminders

**IMPORTANT ROUTING LOGIC:**

| Owner | Notion Action Item | Apple Reminder |
|-------|-------------------|----------------|
| Seth | ✅ Create | ✅ "Work" list |
| Other person + Seth needs to follow up | ✅ Create | ✅ "Work Follow Ups" list |
| Other person + Seth does NOT need to follow up | ✅ Create | ❌ None |

**Seth's Direct Reports (follow-up candidates):**
- Hunter, Kory, Matt, Elizabeth, Tim, Michael, Sergio, Dave, Yanshen, Chiku

**Create "Work Follow Ups" reminder when:**
- Owner is a **direct report** AND item is high priority or has a near-term deadline
- Item **blocks Seth's work** (dependencies, deliverables Seth needs)
- **High-stakes commitment** (leadership visibility, customer-facing, critical deadlines)
- Item has **explicit "follow up" language** in the text (e.g., "Seth to follow up with X")

**DO NOT create Apple Reminder when:**
- Owner is Nick, peers, or other teams → Notion tracking only
- Item is informational/FYI → Notion tracking only
- Owner is a direct report but it's low priority or far-out deadline → Notion tracking only
- Item is routine/standard work → Notion tracking only
- Seth is just an observer → Notion tracking only

**Default to conservative:** When in doubt, put it in Notion only. Seth can always check Notion Action Items for full view. Apple Reminders should be his **need-to-act** list, not a duplicate of everything.

### Seth's Items → "Work" List

**Only create if Owner = "Seth" AND at least one is true:**
- Due date within 7 days
- Priority = High
- Explicit blocker/dependency for another deliverable

If none of the above are true, keep in Notion only (no Apple reminder).

```bash
remindctl add "[Task description]" \
  --list "Work" \
  --due "YYYY-MM-DD" \
  --notes "From meeting: [Meeting Title] (YYYY-MM-DD)

Notion: [link to Action Item page]"
```

### Follow-Up Items → "Work Follow Ups" List

**Only create if Owner ≠ "Seth" AND meets follow-up criteria above:**

```bash
remindctl add "Follow up: [Task] - [Person]" \
  --list "Work Follow Ups" \
  --due "YYYY-MM-DD" \
  --notes "Owner: [Person]
From meeting: [Meeting Title]

Notion: [link to Action Item page]"
```

## Step 7: Update State File

After successfully processing a meeting, add its ID to the state file:

```bash
STATE_FILE="$HOME/.openclaw/workspace/.state/action-items-state.json"

# Add meeting ID to processed list
jq --arg meeting_id "$MEETING_ID" \
   --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
   '.processedMeetings += [$meeting_id] | .lastRun = $timestamp' \
   "$STATE_FILE" > /tmp/state.json && mv /tmp/state.json "$STATE_FILE"
```

**State retention:** Keep meetings from last 30 days to allow reprocessing if needed.

## Step 8: Update Daily Note

Find or create today's Daily Note and add links to new action items:

```bash
# Find today's note
curl -s -X POST "https://api.notion.com/v1/data_sources/NOTION_ID_REDACTED/query" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{
    "filter": {
      "property": "Date",
      "date": {"equals": "2026-01-29"}
    }
  }'

# Add links to new action items
curl -s -X PATCH "https://api.notion.com/v1/blocks/{daily_note_id}/children" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d '{
    "children": [
      {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
          "rich_text": [
            {"type": "mention", "mention": {"page": {"id": "action_item_id"}}},
            {"type": "text", "text": {"content": " - Task description (Owner, due date)"}}
          ]
        }
      }
    ]
  }'
```

## Step 9: Report Results

**Telegram summary format:**

```
📋 Action Items Extracted

From 5 recent meetings:

**Notion Action Items:** 6 added

**Apple Reminders:**
• Work list: 2 items (Seth's tasks)
• Work Follow Ups: 1 item (tracking others)
• Notion only: 3 items (no reminder needed)

Seth's tasks (Work list):
• Review AgentCore proposal (due Fri)
• Schedule security audit (due next week)

Follow-ups (Work Follow Ups):
• Budget approval - Elizabeth (due Mon)

Notion only (no reminder):
• Update documentation - Team
• Review proposal - Nick (FYI only)
• Research options - Kory (low priority)

Skipped 2 duplicates
```

**Be explicit about:**
- How many items went to each destination
- WHY items are "Notion only" (not Seth's, FYI, low priority, etc.)
- Make it clear that fewer reminders = intentional filtering, not an error

## Automation

**Cron schedule:** 12:30 PM and 6:30 PM EST (weekdays)

**Manual trigger:** "check my action items" or "extract action items"

## Error Handling

| Error | Action |
|-------|--------|
| No recent meetings | Report "no meetings found" |
| Meeting has no content | Skip, continue to next |
| Can't parse owner | Default to "Seth" or "Team" |
| API rate limit | Back off, retry |
