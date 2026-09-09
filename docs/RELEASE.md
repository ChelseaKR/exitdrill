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

## Checking what you downloaded

Every release carries a `SHA256SUMS` asset beside the wheel and the source
archive. Download all three into one directory and run `sha256sum -c
SHA256SUMS` there. It is tamper evidence over the transport, not a signature:
whoever can replace the assets can replace the checksum file with them, and
this project publishes no artifact signature (that is one of the preconditions
listed above).

`v0.1.0`'s `SHA256SUMS` does not work that way. Its two digests are correct and
both filenames read `dist/<asset>`, the build directory they were computed in,
so the command above reports each asset as a file it cannot open and exits 1.
Strip the `dist/` prefix and both lines verify. The workflow now writes the
names relative to that directory, and
`tests/test_gates.py::test_the_published_checksums_verify_the_assets_a_reader_downloaded`
runs the workflow's own recipe and checks the result from a flat directory, so
the next release is checkable as published.
