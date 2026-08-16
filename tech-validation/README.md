# SiliconFlow Task Platform Technical Validation

This package contains read-only probes, local business-rule simulations, and
evidence collected for the proposed Taobao-to-task workflow.

## Safety boundary

- The default probe performs GET requests only.
- It does not send SMS messages, submit OTPs, solve CAPTCHAs, create orders,
  register users, or trigger payments.
- OTPs and SiliconFlow session tokens must never be passed on a command line or
  written to a report.
- Live login validation requires a separately approved, supervised test using
  test accounts owned by the participants.

## Run

PowerShell 7 or Windows PowerShell 5.1:

```powershell
powershell -ExecutionPolicy Bypass -File .\run-validation.ps1
```

Linux with PowerShell 7 installed:

```bash
./run-validation.sh
```

Or run each check independently:

```powershell
powershell -ExecutionPolicy Bypass -File .\probe.ps1
powershell -ExecutionPolicy Bypass -File .\test-task-rules.ps1
powershell -ExecutionPolicy Bypass -File .\test-task-concurrency.ps1
python .\test-session-security.py
powershell -ExecutionPolicy Bypass -File .\test-sensitive-output.ps1
```

Generated JSON evidence is written under `evidence/`. Sensitive values are
redacted by the scripts.

## Files

- `probe.ps1`: read-only website and endpoint inventory.
- `run-validation.ps1`: one-command validation runner and summary generator.
- `test-task-rules.ps1`: local simulation of slot, timeout, late-completion, and
  payout rules.
- `test-task-concurrency.ps1`: concurrent contention tests for `N=1/5/10`,
  duplicate claims, and late-completion races.
- `test-session-security.py`: synthetic AES-GCM, AAD binding, tamper, revocation,
  expiry, and 24-hour TTL tests.
- `test-sensitive-output.ps1`: scans Markdown and JSON deliverables for phone
  numbers and credential-like values.
- `validation-report.md`: consolidated findings and Go/No-Go decision.
- `live-test-runbook.md`: supervised steps that require a real test phone.
- `siliconflow-authorization-request.md`: written authorization request template.
- `agent-official-silicon-client.md`: official client and public API audit.
- `agent-silicon-audit.md`: independent reference-site protocol audit.
- `agent-taobao-compliance.md`: Taobao integration and entity-compliance audit.
- `agent-security-qa.md`: threat model, privacy design, and QA gates.
