# Contributing

Read `AGENTS.md`, [the architecture doc](docs/ARCHITECTURE.md), and
[the threat model](docs/THREAT-MODEL.md) first.

```sh
make install
make hooks
make verify
make demo
make demo-directus-canary
```

`make hooks` installs the hooks `.pre-commit-config.yaml` declares. It runs
`pre-commit install` **and** `pre-commit install --hook-type pre-push`,
because the plain form installs only the `pre-commit` hook and the strict
mypy hook is declared `stages: [pre-push]`. Without the second command that
hook is configured and never runs. CI runs `make verify` regardless, so the
hooks are a faster local signal rather than the gate of record.

`make lint-lab` additionally syntax-checks every committed browser-lab script
and needs Node; CI always runs it. The pytest gate repeats that per-script check
and skips it when Node is absent, so `make verify` still needs no browser,
container, or network.

Every input, parser, path, restore, adapter, or receipt change needs a negative
test. Fixtures must be invented and synthetic. Do not add live credentials,
production connectors, general executable transforms, or stronger assurance
labels without an accepted ADR.

## Commercial solicitation

Issues here are not open to bids. They are design records — written so a decision is
reconstructable later — not scope documents for outside quoting, and unsolicited offers to
implement one for a fee will be declined.

Contributions through the normal fork-and-PR process are welcome, and `good first issue` is the
place to start.
