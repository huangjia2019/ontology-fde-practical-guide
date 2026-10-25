# Companion repository working agreement

- The governed assets in `config/` and executable implementation in `src/ontology_fde/`
  are the source of truth.
- Keep the business invariant at **RMB 500**: only when all other requirements pass, `amount <= 500` may be auto-approved;
  `amount > 500` must enter human approval.
- The Agent acts `as_itself` with technical identity `agent.cs.refund.001`.
- A model may propose an action, but only the deterministic policy and contract layer may
  authorize a write.
- Preserve the Read → Draft → Write separation. Tests must prove that Read and Draft do not
  mutate business state.
- Every write outcome, including rejection and human routing, must produce a Decision Record.
- Mock data is synthetic, not extracted from customer systems. Preserve source lineage when adding a record.
- A query returning `not_found` leaves the business conclusion `unknown`; it does not confirm absence.
- Keep reader documentation in plain Chinese, with observable results and accurate implementation limits.
- Do not include credentials, private manuscripts, customer records, or personal filesystem paths.
- Run `python3 tools/verify.py` before release. Screenshot regeneration is optional maintenance work and uses Playwright; normal operation has no third-party runtime dependency.
