# Contributing

Read `AGENTS.md`, the PRD, architecture, and threat model first.

```sh
make install
make verify
make demo
```

Every input, parser, path, restore, adapter, or receipt change needs a negative
test. Fixtures must be invented and synthetic. Do not add live credentials,
production connectors, general executable transforms, or stronger assurance
labels without an accepted ADR.
