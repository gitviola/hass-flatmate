# Session Context

## User Prompts

### Prompt 1

Implement the following plan:

# Plan: Fix rotation race condition + Add reset endpoint

## Context

Two issues to address:
1. **Race condition bug**: When HA polls multiple endpoints concurrently at startup, two requests can both find no `rotation_config` row via `session.get()` and both try to INSERT `id=1`, causing `UNIQUE constraint failed`. This blocks `GET /v1/cleaning/current`.
2. **Reset endpoint**: User needs a way to wipe all data (except members) before re-importing history, to ensure...

### Prompt 2

imported history references members that no longer exist in the members table? -> YES of course!!! that's the whole point of importing the history

### Prompt 3

And yes of course write a test for this.. to make sure all this properly works the import as expected etc

### Prompt 4

Just that those don't have an home assistant id those members that we import I guess.. and we cannot just pick a random one as perhaps the next user created in home assistant once someone moves in perhaps gets that id assigned by hass

### Prompt 5

Hmm why the reset doesnt delete the members I'm wondering? I mean if we want to reset everything perhaps we want to reset everything..

### Prompt 6

yes commit and create release etc

