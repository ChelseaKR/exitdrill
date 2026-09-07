# Release posture

ExitDrill is a technical alpha, first tagged `v0.1.0`. Local wheels and source archives are
test artifacts, not package-registry publication. The practical naming screen
permits creating a source repository named `exitdrill`.

The committed CI workflow verifies code, both synthetic outcomes, packaging,
runtime dependency exposure, secrets, SAST, and workflow safety.

`release.yml` is `workflow_dispatch` only. Pushing a `v*` tag builds nothing: a
maintainer dispatches the workflow with a tag that already exists, and the
shared authorization workflow verifies the annotated tag object, its SSH
signature, and that the tagged commit is an ancestor of `origin/main` before
anything is built.

Two of its gates cost a file read each — the tag has to match the package
version, and `CHANGELOG.md` has to carry a `## [<version>]` section with
content under it, which becomes the release notes. Both run before
`uv sync`, so a release with no notes is refused in seconds rather than after
`make verify`, both demos and the wheel build. `make release-preflight
TAG=vX.Y.Z` asks the same two questions from a working copy, before the tag is
cut.

Public or package-registry publication remains blocked until all of these exist:

- initialized version control and a hosted private repository;
- protected main and tag rulesets with required checks;
- an independently reviewed release decision;
- signed tags and verified maintainer identity;
- SBOM, artifact signature, and provenance;
- private vulnerability reporting and incident labels;
- exact package URLs and security contact route; and
- attorney review of the practical name-clearance memo before trademark filing
  or material commercial brand investment.

The release workflow's publish job holds `contents: write` and creates a GitHub
Release from the verified tag; it never checks out code. It holds no registry
credential and no trusted publisher is configured, so package-registry
publication is out of scope for it entirely.
