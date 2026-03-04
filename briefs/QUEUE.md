# CopyAgent Brief Queue

## Active Briefs
| ID | Priority | Type | Title | Status | Deadline |
|----|----------|------|-------|--------|----------|
| BRIEF-0001 | HIGH | email | Cold CEO sequence refresh | PENDING | 2026-03-07 |
| BRIEF-0002 | HIGH | blog | Proc pruzkumy nefunguji | PENDING | 2026-03-08 |
| BRIEF-0003 | MEDIUM | linkedin | Echo Pulse launch post series | PENDING | 2026-03-10 |

## Completed
(none yet)

## How This Works
1. Briefs are added here by any agent or by Josef
2. CopyAgent checks this file on every heartbeat
3. CopyAgent picks the highest-priority PENDING brief
4. Moves status to IN_PROGRESS
5. Writes output to drafts/
6. Moves status to REVIEW
7. After Josef approves, moves to DONE
