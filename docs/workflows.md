# The workflows, drawn from their files

Made by `scripts/build_docs.py` from `n8n/*.json` (the files `scripts/build_n8n.py` writes and `scripts/n8n_publish.py` puts into n8n). Each diagram's numbers are its step list's numbers. Every workflow starts from a form, by hand: none has a schedule. Every write goes through one of the store's checked functions. Nothing sends: an approved update goes to the outbox table only. `tests/test_build_docs.py` fails if this page differs from the files.

## Change Desk: intake form

File `n8n/intake.json`; form `/form/changedesk-intake`; 5 nodes; 0 AI steps; writes through `add_request`.

```mermaid
flowchart TD
  s1(["1. Request Form"])
  s2["2. Make Request"]
  s3[("3. Add Request")]
  s4["4. Done Message"]
  s5(["5. Done"])
  s1 --> s2
  s2 --> s3
  s3 --> s4
  s4 --> s5
```

1. **Request Form** (form, started by hand): Change Desk: ask for a change
2. **Make Request** (code): The form's answers, as the store's add_request function takes them. The text is data: nothing here reads it as instructions.
3. **Add Request** (store): writes through add_request
4. **Done Message** (code): the words of the closing message
5. **Done** (form page): the closing message

## Change Desk: run triage

File `n8n/triage.json`; form `/form/changedesk-triage`; 16 nodes; 1 AI step; writes through `log_triage`.

```mermaid
flowchart TD
  s1(["1. Start Triage"])
  s2[("2. Read Inbox")]
  s3[("3. Read Goals")]
  s4[("4. Read Settings")]
  s5["5. Build Requests"]
  s6{"6. Anything to Triage?"}
  s7[["7. Loop Over Requests"]]
  s8["8. Stamp Start"]
  s9{{"9. Claude Triage Step"}}
  s10["10. Check Triage"]
  s11["11. Collect"]
  s12[("12. Log Triage")]
  s13[("13. Read Run Summary")]
  s14["14. Done Message"]
  s15(["15. Done"])
  s16["16. Nothing Message"]
  s1 --> s2
  s2 --> s3
  s3 --> s4
  s4 --> s5
  s5 --> s6
  s6 -->|yes| s7
  s6 -->|no| s16
  s7 -->|all done| s11
  s7 -->|next one| s8
  s8 --> s9
  s9 --> s10
  s10 --> s7
  s11 --> s12
  s12 --> s13
  s13 --> s14
  s14 --> s15
  s16 --> s15
```

1. **Start Triage** (form, started by hand): Change Desk: run triage
2. **Read Inbox** (store): reads inbox
3. **Read Goals** (store): reads goals
4. **Read Settings** (store): reads settings
5. **Build Requests** (code): One Claude request per request in the inbox. The text goes inside a data block, after the guard rules.
6. **Anything to Triage?** (check)
7. **Loop Over Requests** (one at a time)
8. **Stamp Start** (code): notes when the AI call starts
9. **Claude Triage Step** (Claude API, the one AI step): one Messages call, Haiku 5.5, structured output
10. **Check Triage** (code): The guard rails: the fixed shape, the lane rule, the confidence bar, the split, the code screen, the stamp.
11. **Collect** (code): the engine's `triageHandoff`, `summariseTriage`
12. **Log Triage** (store): writes through log_triage
13. **Read Run Summary** (store): reads run_summary
14. **Done Message** (code): the words of the closing message
15. **Done** (form page): the closing message
16. **Nothing Message** (code): the words of the closing message

## Change Desk: confirm lanes

File `n8n/confirm-lanes.json`; form `/form/changedesk-confirm-lanes`; 10 nodes; 0 AI steps; writes through `confirm_lanes`.

```mermaid
flowchart TD
  s1(["1. Start Confirmation"])
  s2[("2. Read Waiting")]
  s3["3. Build Form"]
  s4{"4. Anything Waiting?"}
  s5(["5. Lane Confirmation"])
  s6["6. Apply Choices"]
  s7[("7. Confirm Lanes")]
  s8["8. Done Message"]
  s9(["9. Done"])
  s10["10. Nothing Message"]
  s1 --> s2
  s2 --> s3
  s3 --> s4
  s4 -->|yes| s5
  s4 -->|no| s10
  s5 --> s6
  s6 --> s7
  s7 --> s8
  s8 --> s9
  s10 --> s9
```

1. **Start Confirmation** (form, started by hand): Change Desk: confirm lanes
2. **Read Waiting** (store): reads awaiting_confirmation
3. **Build Form** (code): the engine's `buildConfirmForm`
4. **Anything Waiting?** (check)
5. **Lane Confirmation** (form page): Confirm the lanes
6. **Apply Choices** (code): the engine's `applyConfirmations`
7. **Confirm Lanes** (store): writes through confirm_lanes
8. **Done Message** (code): the words of the closing message
9. **Done** (form page): the closing message
10. **Nothing Message** (code): the words of the closing message

## Change Desk: change a score

File `n8n/change-score.json`; form `/form/changedesk-change-score`; 11 nodes; 0 AI steps; writes through `change_score`.

```mermaid
flowchart TD
  s1(["1. Start Score Change"])
  s2[("2. Read Ranked")]
  s3[("3. Read Working")]
  s4["4. Build Form"]
  s5{"5. Anything Ranked?"}
  s6(["6. Score Change"])
  s7["7. Apply Change"]
  s8[("8. Change Score")]
  s9["9. Done Message"]
  s10(["10. Done"])
  s11["11. Nothing Message"]
  s1 --> s2
  s2 --> s3
  s3 --> s4
  s4 --> s5
  s5 -->|yes| s6
  s5 -->|no| s11
  s6 --> s7
  s7 --> s8
  s8 --> s9
  s9 --> s10
  s11 --> s10
```

1. **Start Score Change** (form, started by hand): Change Desk: change a score
2. **Read Ranked** (store): reads standard_ranked
3. **Read Working** (store): reads score_working, standard_ranked
4. **Build Form** (code): the engine's `buildScoreForm`
5. **Anything Ranked?** (check)
6. **Score Change** (form page): Change one part of a score
7. **Apply Change** (code): the engine's `applyScoreChange`
8. **Change Score** (store): writes through change_score
9. **Done Message** (code): the words of the closing message
10. **Done** (form page): the closing message
11. **Nothing Message** (code): the words of the closing message

## Change Desk: decide list

File `n8n/decide.json`; form `/form/changedesk-decide`; 20 nodes; 1 AI step; writes through `decide`, `log_drafts`.

```mermaid
flowchart TD
  s1(["1. Start Decide List"])
  s2[("2. Read Decide List")]
  s3[("3. Read Open Items")]
  s4["4. Build Form"]
  s5{"5. Anything Past Its Limit?"}
  s6(["6. Decide"])
  s7["7. Apply Choices"]
  s8[("8. Record Decisions")]
  s9["9. Build Drafts"]
  s10{"10. Anything Closed?"}
  s11[["11. Loop Over Closes"]]
  s12["12. Stamp Start"]
  s13{{"13. Claude Message Drafter"}}
  s14["14. Check Draft"]
  s15["15. Collect Drafts"]
  s16[("16. Log Drafts")]
  s17["17. Done Message"]
  s18(["18. Done"])
  s19["19. No Close Message"]
  s20["20. Nothing Message"]
  s1 --> s2
  s2 --> s3
  s3 --> s4
  s4 --> s5
  s5 -->|yes| s6
  s5 -->|no| s20
  s6 --> s7
  s7 --> s8
  s8 --> s9
  s9 --> s10
  s10 -->|yes| s11
  s10 -->|no| s19
  s11 -->|all done| s15
  s11 -->|next one| s12
  s12 --> s13
  s13 --> s14
  s14 --> s11
  s15 --> s16
  s16 --> s17
  s17 --> s18
  s19 --> s18
  s20 --> s18
```

1. **Start Decide List** (form, started by hand): Change Desk: decide list
2. **Read Decide List** (store): reads decide_list
3. **Read Open Items** (store): reads requests
4. **Build Form** (code): the engine's `buildDecideForm`
5. **Anything Past Its Limit?** (check)
6. **Decide** (form page): Decide the old items
7. **Apply Choices** (code): the engine's `applyDecideChoices`
8. **Record Decisions** (store): writes through decide
9. **Build Drafts** (code): One message draft per closed item. The drafter sees the title, the role and the reason: no score, no request text.
10. **Anything Closed?** (check)
11. **Loop Over Closes** (one at a time)
12. **Stamp Start** (code): notes when the AI call starts
13. **Claude Message Drafter** (Claude API, the one AI step): one Messages call, Haiku 5.5, structured output
14. **Check Draft** (code): The draft is checked in code before anyone sees it: the request id is named, no internal codes, no promise, no contact details.
15. **Collect Drafts** (code)
16. **Log Drafts** (store): writes through log_drafts
17. **Done Message** (code): the words of the closing message
18. **Done** (form page): the closing message
19. **No Close Message** (code): the words of the closing message
20. **Nothing Message** (code): the words of the closing message

## Change Desk: approve updates

File `n8n/approve-updates.json`; form `/form/changedesk-approve-updates`; 10 nodes; 0 AI steps; writes through `approve_updates`.

```mermaid
flowchart TD
  s1(["1. Start Approval"])
  s2[("2. Read Drafts")]
  s3["3. Build Form"]
  s4{"4. Anything to Approve?"}
  s5(["5. Approval"])
  s6["6. Apply Choices"]
  s7[("7. Approve Updates")]
  s8["8. Done Message"]
  s9(["9. Done"])
  s10["10. Nothing Message"]
  s1 --> s2
  s2 --> s3
  s3 --> s4
  s4 -->|yes| s5
  s4 -->|no| s10
  s5 --> s6
  s6 --> s7
  s7 --> s8
  s8 --> s9
  s10 --> s9
```

1. **Start Approval** (form, started by hand): Change Desk: approve updates
2. **Read Drafts** (store): reads stale_facts, updates, requests
3. **Build Form** (code): Drafts with a problem from the code check, or whose facts no longer match their rows, can only be rejected.
4. **Anything to Approve?** (check)
5. **Approval** (form page): Approve the updates
6. **Apply Choices** (code): the engine's `applyApprovals`
7. **Approve Updates** (store): writes through approve_updates
8. **Done Message** (code): the words of the closing message
9. **Done** (form page): the closing message
10. **Nothing Message** (code): the words of the closing message
