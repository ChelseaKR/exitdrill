# Contributing

Read `AGENTS.md`, the PRD, architecture, and threat model first.

```sh
make install
make verify
make demo
make demo-directus-canary
```

`make lint-lab` additionally syntax-checks every committed browser-lab script
and needs Node; CI always runs it. The pytest gate repeats that per-script check
and skips it when Node is absent, so `make verify` still needs no browser,
container, or network.

Every input, parser, path, restore, adapter, or receipt change needs a negative
test. Fixtures must be invented and synthetic. Do not add live credentials,
production connectors, general executable transforms, or stronger assurance
labels without an accepted ADR.
