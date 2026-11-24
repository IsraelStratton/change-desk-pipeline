# Role card: the message drafter

KB-137 A1.4. The drafter is shaped from the GTM pipeline's message drafter (its guard rules and its code check of every draft). In stages 0 to 2 it drafts one kind of message: the note to a requester when a person closes their old request from the decide list (R16). Stage 5 adds the updates for three audiences.

| Item | This agent |
|---|---|
| **Name** | Message drafter (the "Claude Message Drafter" in the n8n workflow "Change Desk: decide list") |
| **Purpose** | When a person closes an old request with a reason, write a short, kind, plain message to the requester: what was asked, that it is closed and why, and how to ask again |
| **Named owner** | Systems desk lead: a made-up role in this build |
| **What it reads** | The request id and title, the requester's role, the date it was asked, and the person's reason for closing. Not the request text, not a score, not a lane |
| **What it writes** | Nothing. It returns a subject and a body. The workflow checks the draft in code and logs it through `changedesk.log_drafts` as a draft, with a stamp. Nobody sends it: a person approves drafts in stage 5, and even then an approved update goes only to the outbox table |
| **What it must never do** | Send anything; change the decision; add reasons, promises or dates of its own; mention scores, lanes, codes, the AI or how the desk works inside; name or judge a person; repeat contact details |
| **Tools** | None. A single Claude Messages call with structured outputs. Model `claude-haiku-5-5`, effort `low` |
| **Brief** | In [`engine/drafter.js`](../../engine/drafter.js) (`close-message` 1.0.0); its SHA-256 is logged with every call |
| **Guard rails** | The record goes in as escaped JSON inside a data block. Code checks every draft before anyone sees it: it names the request id; no internal words (score, lane, playbook, AI); no promise; no contact details; not a copy of the instructions; within the length limits. A draft that fails a check is kept with its problems listed, for a person to see |
| **Approval point** | Stage 5's review form. Until then a draft only waits in `changedesk.updates` with status `draft`; the app's login cannot approve or send one |
| **Stop switch** | Nothing is scheduled. The drafter runs only when a person closes an item on the decide form. `python scripts/n8n_publish.py off` stops every workflow |
| **Spend limit** | The workspace `gtm-pipeline` has a US$10 monthly limit. Cost per draft: see [`docs/cost-sheet.md`](../cost-sheet.md) |
| **Evidence** | `changedesk.run_log` (step `drafter`), `changedesk.updates` (the draft, its problems, its stamp), `changedesk.agent_handoffs` (from the person's decision to the drafter) |
| **Review date** | At stage 5, when it gains the three audiences |
