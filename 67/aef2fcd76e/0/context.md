# Session Context

## User Prompts

### Prompt 1

Implement the following plan:

# Resilient Cleaning Notifications

## Context

Cleaning notifications currently fire only at exact minute matches (e.g., Monday 11:00:00). If HA restarts at that minute, the notification is silently lost with no retry. There's also no Sunday morning reminder — only evening ones at 18:00 and 21:00. Additionally, when a previous week's shift is missed, the old assignee never gets told.

## Approach

Track sent notification slots directly on `CleaningAssignment` vi...

### Prompt 2

yes and create a new release of course pls

### Prompt 3

Pls do so

### Prompt 4

pls remove those not needed steps inside the publish gh action.. I mean this attempt to set package visibility public and this weird verify anonymous pull works for both ach.. We found the issue long time ago so it was a pefix issue

