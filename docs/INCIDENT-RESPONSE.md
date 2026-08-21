# Incident response

ExitDrill is not deployed, but data exposure, credential exposure, a false
strong restoration result, or a disabled security gate can still be an
incident.

1. Stop the affected workflow and preserve non-sensitive diagnostic facts.
2. If a credential may be exposed, rotate it, revoke the old value, and inspect
   issuer audit logs before considering repository-history cleanup.
3. If real data was processed contrary to policy, isolate the workspace, stop
   copying it, identify every storage location, and obtain legal/privacy advice
   before deletion could destroy required evidence.
4. Correct the control and add a regression test.
5. Record confirmed incidents under `docs/incidents/YYYY-MM-DD-<slug>.md` with
   severity, UTC timeline, impact, detection, systemic root cause, actions,
   owners, and due dates.

Never include credentials, production exports, personal data, or confidential
attachment content in an issue or postmortem.
