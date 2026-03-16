# 1:1 Meeting Prep Skill (Notion)

**Triggers:** "prep for my 1:1 with [name]", "prepare for meeting with [name]", "1:1 prep [name]"

## Overview

Creates a 1:1 prep document by gathering context from Notion databases (People, Knowledge Hub, Action Items) and storing the result in the 1:1 Prep database.

## Notion Configuration

**Important:** Notion API has two types of IDs:
- **Data Source ID** - Use with API version `2025-09-03` for querying
- **Database ID** - Use with API version `2022-06-28` for page creation

**People:**
- Data Source ID: `NOTION_ID_REDACTED`
- Database ID: `NOTION_ID_REDACTED`
- Properties: Name, Role, Team, Current Focus, Last 1:1, Next 1:1, Relationship, Communication Style

**Knowledge Hub:**
- Data Source ID: `NOTION_ID_REDACTED`
- Database ID: `NOTION_ID_REDACTED`
- Filter: Type = "Meeting" for meeting notes

**Action Items:**
- Data Source ID: `NOTION_ID_REDACTED`
- Database ID: `NOTION_ID_REDACTED`
- Properties: Task, Owner, Status, Due Date, Priority, Category, Source Meeting

**1:1 Prep:**
- Data Source ID: `NOTION_ID_REDACTED`
- Database ID: `NOTION_ID_REDACTED`
- Properties: Name, Person (relation), Date, Status

**Daily Notes:**
- Data Source ID: `NOTION_ID_REDACTED`
- Database ID: `NOTION_ID_REDACTED`

## Step 1: Extract Person Name

Parse the person's name from the request:
- "prep for my 1:1 with Matt" → Matt
- "1:1 prep Elizabeth" → Elizabeth
- "prepare for meeting with Nick Nocerino" → Nick Nocerino

## Step 2: Find Person in Notion

Query People database (use Data Source ID + API 2025-09-03):

```bash
NOTION_KEY=$(cat ~/.config/notion/api_key  # create this file locally with your key)

curl -s -X POST "https://api.notion.com/v1/data_sources/NOTION_ID_REDACTED/query" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{
    "filter": {
      "property": "Name",
      "title": {"contains": "Matt"}
    }
  }'
```

Extract from result:
- `id`: Person page ID (needed for relation)
- `Name`: Full name
- `Role`: Their role/title
- `Team`: Their team
- `Current Focus`: What they're working on
- `Last 1:1`: When we last met
- `Communication Style`: How to approach them

## Step 3: Find Recent Meetings

Query Knowledge Hub for meetings mentioning this person (use Data Source ID):

```bash
curl -s -X POST "https://api.notion.com/v1/data_sources/NOTION_ID_REDACTED/query" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{
    "filter": {
      "and": [
        {"property": "Type", "select": {"equals": "Meeting"}},
        {"property": "Date", "date": {"past_month": {}}}
      ]
    },
    "sorts": [{"property": "Date", "direction": "descending"}],
    "page_size": 20
  }'
```

Then search through results for meetings that mention the person's name.

## Step 4: Get Open Action Items

Query Action Items for items related to this person (use Data Source ID):

```bash
curl -s -X POST "https://api.notion.com/v1/data_sources/NOTION_ID_REDACTED/query" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2025-09-03" \
  -H "Content-Type: application/json" \
  -d '{
    "filter": {
      "and": [
        {"property": "Owner", "select": {"equals": "Person Name"}},
        {"property": "Status", "select": {"does_not_equal": "Done"}}
      ]
    }
  }'
```

Categorize:
- **From them:** Action items they own
- **For them:** Action items Seth owns that involve them

## Step 5: Compile Prep Content

Structure the gathered information:

### Hot Topics to Follow Up On
- Unresolved discussions
- Decisions that need follow-up
- Projects in progress
- Any concerns or blockers mentioned

### Open Action Items
List items grouped by owner.

### Recent Meetings
List the most recent 3-5 relevant meetings with brief summaries.

### Context
- Org changes affecting them
- Upcoming deadlines
- Career development topics

## Step 6: Create 1:1 Prep Page

Create page in 1:1 Prep database (use Database ID + API 2022-06-28):

```bash
curl -s -X POST "https://api.notion.com/v1/pages" \
  -H "Authorization: Bearer $NOTION_KEY" \
  -H "Notion-Version: 2022-06-28" \
  -H "Content-Type: application/json" \
  -d '{
    "parent": {"database_id": "NOTION_ID_REDACTED"},
    "properties": {
      "Name": {"title": [{"text": {"content": "1:1 Prep: Nick Nocerino - Jan 29, 2026"}}]},
      "Person": {"relation": [{"id": "person_page_id"}]},
      "Date": {"date": {"start": "2026-01-29"}},
      "Status": {"select": {"name": "Active"}}
    },
    "children": [
      {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"text": {"content": "🔥 Hot Topics to Follow Up On"}}]}},
      // ... more blocks
    ]
  }'
```

## Step 7: Update Daily Note

Find or create today's Daily Note, then add a link (use appropriate IDs):

```bash
# Find (use Data Source ID)
curl -s -X POST "https://api.notion.com/v1/data_sources/NOTION_ID_REDACTED/query" ...

# Add block (use page ID from result + API 2022-06-28)
curl -s -X PATCH "https://api.notion.com/v1/blocks/{daily_note_id}/children" \
  -H "Notion-Version: 2022-06-28" ...
```

## Step 8: Send Telegram Summary

```
🤝 1:1 Prep Ready: [Person Name]

🔥 Hot Topics:
1. [Topic 1] - [one-line context]
2. [Topic 2] - [one-line context]

📋 Open Items: [X] from them, [Y] for them

📅 Recent: [N] meetings in past 30 days

View in Notion: [link to prep page]
```

## Error Handling

| Error | Action |
|-------|--------|
| Person not found | Ask for clarification or offer to create |
| No recent meetings | Note in prep, still create doc |
| No action items | Note "No open action items" |
| API error | Log error, report to user |
