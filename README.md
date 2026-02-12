# Automated API Testing Framework

Production-oriented, invariant-driven API testing framework for finding systemic correctness bugs (idempotency breaks, negative balances, and state drift) instead of only response-code mismatches.

## Features

- YAML-driven endpoint/test configuration
- HTTP request engine with latency capture
- State snapshots and invariant checks
- Retry simulation for idempotency violations
- Fuzz testing for invalid and boundary inputs
- Stateful sequence testing across multi-step flows
- Terminal report with pass/fail summary

## Project Layout

```text
Automated API Testing Framework/
├── api_test_framework/
├── mock_server/
├── tests/
├── .github/workflows/ci.yml
├── main.py
├── requirements.txt
└── README.md
```

## Install

```bash
python3 -m pip install -r requirements.txt
```

## Run Mock Server

```bash
python3 -m mock_server.bank_api
```

Optional environment flags:

- `BANK_BUG_ALLOW_NEGATIVE=1`
- `BANK_BUG_DUPLICATE_ON_RETRY=1`

## Run Framework

Bug-demo scenario (expected failures):

```bash
python3 main.py tests/transfer_test.yaml
```

Clean scenario (expected pass, used by CI smoke test):

```bash
python3 main.py tests/transfer_test_ci.yaml
```

Optional report file:

```bash
python3 main.py tests/transfer_test.yaml --report-file report.txt
```

## Automated Tests

Run unit tests:

```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

## CI

GitHub Actions workflow at `.github/workflows/ci.yml` performs:

- dependency install
- compile check
- unit tests
- end-to-end smoke run against `tests/transfer_test_ci.yaml`

## Notes

- `tests/transfer_test.yaml` intentionally enables bug flags to demonstrate invariant failures.
- `tests/transfer_test_ci.yaml` disables those bug flags so CI can enforce a passing baseline.
