# Publishing Fernz to PyPI

Adam: configure the GitHub environment and PyPI publisher below **before pushing
any release tag**. Merging the workflow does not configure either account.
Pushing `v0.0.1` is an actual production release, not a test. This guide does not
claim that the `fernz` name is available or that account setup has been completed.

## Model and release contract

The reference repository is **[afourney/jlv](https://github.com/afourney/jlv)**,
not `afourney/JVL`. Its inspected
[release workflow at commit 56bde3c6](https://github.com/afourney/jlv/blob/56bde3c6de90c585c948ec47f502fef0356df864/.github/workflows/release.yml)
uses `v*` tag pushes, a build/artifact handoff, a `pypi` environment, and PyPI
Trusted Publishing (GitHub OIDC). Fernz follows that authentication and release
model. There is **no PyPI API token, password, or GitHub secret to create**.
GitHub generates the short-lived identity used by the publishing action.

Fernz's [release.yml](../.github/workflows/release.yml) does the following:

1. On a pushed `v*` tag, require the complete tag to equal `v` followed by the
   literal `[project].version` in `pyproject.toml`. Currently that version is
   `0.0.1`, so the matching tag is `v0.0.1`. No version is rewritten by CI.
2. Check `uv.lock`, build with Fernz's existing `uv_build` backend, and run
   `poe build-check`. The check requires one pure Python wheel and one sdist,
   validates names/versions, the CLI entry point, Python requirement, license,
   required modules and optional dependency boundary. It rejects game files,
   then installs the wheel outside the checkout and exercises both CLI entry
   points with an independent synthetic story. No game download is needed.
3. Run `twine check --strict` on the two distributions to validate upload metadata
   and README rendering. Upload only the wheel and sdist as the `dist` Actions
   artifact. Downloaded ROMs and test-vector archives are not release artifacts.
4. Only for a tag push in `afourney/fernz`, wait for the `pypi` environment's
   protection rules and publish that run's `dist` artifact to production PyPI.
   The publish job never checks out or builds repository code.

This workflow runs only for pushed `v*` tags. Ordinary pull requests use the
**check** workflow, which retains `poe build-check` packaging validation. A GitHub
Release page is optional; publishing one is not this workflow's trigger.
Non-`v` tags and branch pushes do not trigger this workflow.
A version suffix such as `0.1.0rc1` requires exactly `v0.1.0rc1`; a prefixless,
mismatched, or differently spelled version is not accepted.

The build job has `contents: read`; only the publish job has `id-token: write`
and `actions: read`. The latter follows JLV's artifact retrieval permissions.
`id-token: write` allows requesting an OIDC identity, not writing repository
contents. There is no repository write permission. The publish action uses its
production PyPI default and default attestations for Trusted Publishing.
`skip-existing` is intentionally not enabled: duplicate files are an error.
Same-ref runs are serialized without cancelling an in-progress publication;
different version tags can run independently, so release one version at a time.

The workflow retains JLV's `checkout@v4`, `setup-uv@v5`, artifact actions `@v4`,
and PyPA `@release/v1` references, with Fernz's CI pin of uv `0.12.23` and Python
3.11. These action references track upstream updates; they are not immutable
commit pins. Review action updates as release infrastructure changes.

## 1. Confirm ownership and access

- Adam needs access to administer `afourney/fernz` settings and permission to
  push release tags under the repository's rules. Other release operators need
  tag push access; they do not need personal PyPI upload tokens.
- Sign in to the intended account at **pypi.org**, verify its email, and complete
  PyPI's required two-factor authentication setup. Keep recovery material in
  Adam's own account storage, never in this repository or a PR.
- Look up `fernz` on PyPI while signed in. If it already exists, verify that Adam
  is an **Owner** of that project. A matching GitHub repository name does not
  confer PyPI ownership. If someone else owns it, stop and resolve ownership or
  deliberately change package naming in a separately reviewed change.
- PyPI and TestPyPI are separate services with separate accounts, project names
  and publishers. This workflow targets production PyPI only. Local validation
  and ordinary CI do not prove that PyPI authentication works.

## 2. Configure GitHub, before any release tag

Open [Fernz settings](https://github.com/afourney/fernz/settings).

1. Under **Actions → General**, enable GitHub Actions. If actions are restricted
   to an allowlist, allow the exact actions used in `release.yml`:
   `actions/checkout@v4`, `astral-sh/setup-uv@v5`,
   `actions/upload-artifact@v4`, `actions/download-artifact@v4`, and
   `pypa/gh-action-pypi-publish@release/v1`. Existing CI also needs its own actions.
   Any account or organization policy must permit these actions and OIDC.
2. Keep default workflow permissions read-only. The workflow explicitly grants
   OIDC only to its publish job; do not grant write-all permissions or enable
   Actions to create/approve PRs for this release process.
3. Under **Environments → New environment**, create **`pypi`**. Use this spelling
   consistently in GitHub, the workflow and PyPI.
4. Under that environment's **Deployment branches and tags**, choose **Selected
   branches and tags**. Add a rule with ref type **Tag** and pattern **`v*`**.
   A Branch rule named `v*`, or allowing only branch `main`, does not allow the
   intended tag deployment. Avoid adding branch rules to this environment.
5. Decide the approval policy explicitly:
   - Recommended with another maintainer: add a trusted required reviewer,
     enable **Prevent self-review**, and disable administrator bypass. At least
     one configured reviewer must approve each release. Verify that someone
     other than the tag pusher is actually available to approve.
   - For Adam as the sole maintainer: requiring Adam as reviewer can provide an
     intentional approval pause, but **Prevent self-review must be off** if Adam
     also pushes the tag. Otherwise the release will remain waiting. Alternatively,
     omit required reviewers for fully automatic publishing after a tag push.
   - Protection features depend on repository visibility and GitHub plan; check
     their availability before relying on them. Never silently treat an unavailable
     rule as protection that is in force.
6. Add **no environment secrets and no environment variables** for this workflow.
   Do not add `PYPI_TOKEN`, `PYPI_API_TOKEN`, or a `password` action input.
7. Protect `main` and release tags with repository rules as appropriate: require
   reviewed changes and successful checks on main; limit who can create `v*`
   tags, and restrict updating/deleting existing release tags. Ensure the intended
   release operator is allowed by those rules. A tag pattern alone does **not**
   prove the tag points to reviewed main. The workflow does not check main ancestry
   or wait for other CI workflows; the operator must verify both before tagging.

Create the environment deliberately before release. A workflow referencing a
missing environment can cause GitHub to create one without protection rules.
Adding `environment: pypi` to YAML alone does not provide reviewer protection.

See [GitHub environment configuration](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)
and [GitHub OIDC for PyPI](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-pypi).

## 3. Configure PyPI Trusted Publishing

Use these exact values in the **GitHub** publisher form:

| PyPI field | Value | Must match |
| --- | --- | --- |
| PyPI project name (new project only) | `fernz` | `[project].name`, not the CLI display title |
| Owner | `afourney` | GitHub repository owner |
| Repository name | `fernz` | Repository name only, not a URL or `afourney/fernz` |
| Workflow name / filename | `release.yml` | Filename under `.github/workflows/`, not `release` or a full path |
| Environment name | `pypi` | `jobs.publish.environment.name`; do not leave blank |

**New project:** open [account Publishing](https://pypi.org/manage/account/publishing/),
choose **Add a new pending publisher**, select GitHub, and enter the table above.
The pending publisher creates the project on the first successful publication and
then becomes a regular publisher. It does not reserve the name beforehand. There
is no need to upload a bootstrap release locally or create a temporary API token.
If the name is taken before first use, resolve that issue rather than repeatedly
retrying the workflow.

**Existing project owned by Adam:** open
[fernz Publishing](https://pypi.org/manage/project/fernz/settings/publishing/)
(or Manage project → Publishing), choose **Add a new publisher**, select GitHub,
and enter the four GitHub identity fields above. Do not use a pending publisher
for an existing project. An Owner should perform this setup; being a project
Maintainer or a GitHub administrator alone is not sufficient to manage PyPI
publisher configuration. Preserve any unrelated legitimate publishers.

Confirm the saved entry before tagging. Renaming the repository, workflow file,
or environment later requires updating the PyPI publisher as well. The visible
Actions workflow title `release` and the job ID `publish` are not the workflow
filename field. JLV's `jsonl-viewer` project and `jlv` repository values must not
be copied into Fernz's publisher.

See PyPI's instructions for
[existing projects](https://docs.pypi.org/trusted-publishers/adding-a-publisher/),
[new projects](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/),
and [publishing without a token](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

## 4. Validate without uploading

Run these from a clean checkout of the candidate commit. Use uv 0.12.23, as in CI.
Use a fresh checkout or move previous build output out of `dist/` first; the
checker intentionally rejects multiple wheels or sdists left by older versions.

```sh
uv lock --check
uv sync --frozen --extra textual
uv run --no-sync poe check-all
uvx twine check --strict dist/*
```

These commands do not publish. `poe check-all` runs quality checks, offline tests,
and package validation. The optional Textual frontend is included in these local
tests; the package checker also verifies an installation without that extra.
The backend constraint remains `uv_build>=0.10.2,<0.11.0`; uv may warn that its own
version differs from the backend version, but build isolation installs the
specified backend. Do not update the backend solely to suppress that warning.

The ordinary **check** workflow runs `poe build-check` on pull requests and pushes
to main. Use its build job and the local commands above to validate packaging
before tagging. Do not create a tag to test CI: a matching release tag starts
production publication after the configured environment gates pass. Local
validation and ordinary CI do not validate actual PyPI account permissions.

Before an actual release require the normal **check** workflow and the
**comprehensive** suite to pass on the exact release commit, following
[CI.md](CI.md). The tag-triggered release build is a packaging gate, not the
exhaustive interpreter/reference test suite. See CI.md for comprehensive run
instructions.

Check that the run SHA is the candidate SHA, particularly if main is moving.
All clean-room restrictions in [OVERVIEW.md](OVERVIEW.md#mandatory-clean-room-requirement)
continue to apply. Never inspect Jericho/Frotz implementation source or upload
ROMs as part of release validation.

## 5. Prepare the version, then release deliberately

For the first release, current main already declares `0.0.1`. Keep it only if that
version has never been published and it is the intended release. For later
releases, change the version in a reviewed branch, update the lockfile, and merge
only after checks pass. For example, to prepare a future `0.0.2`:

```sh
git switch -c release/prepare-0.0.2
uv version 0.0.2
uv lock
uv lock --check
git diff -- pyproject.toml uv.lock
```

Commit both version/lockfile changes, open a PR, validate it, and merge it through
the usual review process. Do not bump only a tag or use the release job to edit
version files. Use standard public PEP 440 versions; do not use local `+suffix`
versions for PyPI. Alpha, beta and release-candidate versions are real uploads,
not disposable tests, and must also be unique.

The commands below **publish to production** once all setup and review gates are
satisfied. They are for Adam to run deliberately, not part of a dry run:

```sh
git switch main
git pull --ff-only origin main
git status --short                    # Must be empty
git rev-parse HEAD                    # Record and compare with successful CI SHA
uv lock --check
version=$(uv version --short)
printf 'Proposed release: v%s\n' "$version"
git ls-remote --tags origin "refs/tags/v$version" "refs/tags/v$version^{}"
# Stop if that tag exists or this version already has any PyPI files.
# Confirm this exact commit has passed check, comprehensive, and local packaging checks.
git tag -a "v$version" -m "Fernz $version"
git show --no-patch "v$version"
git push origin "refs/tags/v$version"
```

Push just this tag, not `--tags`. Use Adam's normal authenticated Git push; do not
expect a tag pushed by a workflow's `GITHUB_TOKEN` to trigger another workflow.
Review the new **release** run and confirm its event is `push`, ref is the intended
tag and SHA is the tested commit. If environment approval is enabled, examine
build results and artifacts before approving **Review deployments → pypi**.
Approval starts the production publishing job. Creating a draft GitHub Release
or publishing release notes is not necessary to upload to PyPI.

## 6. Verify the first release

1. Confirm both jobs in the tag-triggered run succeeded. Retain the run URL, tag,
   commit SHA, and artifact for release records.
2. Open `https://pypi.org/project/fernz/VERSION/` with the actual version substituted.
   Check author, MIT license, Python requirement, README rendering and the two
   expected files: `fernz-VERSION-py3-none-any.whl` and `fernz-VERSION.tar.gz`.
   Examine PyPI's provenance/attestation details for the repository/workflow.
3. Compare SHA-256 digests from the PyPI file details with the downloaded Actions
   artifact (`sha256sum dist/*` on Linux). Do not mistake a locally rebuilt wheel
   for the exact bytes uploaded by CI.
4. In a fresh directory/environment, install explicitly from production PyPI,
   bypassing caches and pinning the version. For example, for the initial release:

   ```sh
   uv venv /tmp/fernz-pypi-verify
   uv pip install --python /tmp/fernz-pypi-verify/bin/python --no-cache \
     --index-url https://pypi.org/simple 'fernz==0.0.1'
   /tmp/fernz-pypi-verify/bin/python -I -c \
     "import fernz; from importlib.metadata import version; print(version('fernz'))"
   /tmp/fernz-pypi-verify/bin/fernz --help
   /tmp/fernz-pypi-verify/bin/python -I -m fernz --help
   ```

   Use a new destination if that directory already exists. On Windows, substitute
   the environment's `Scripts/python.exe` and `Scripts/fernz.exe`. Optionally repeat
   in a second environment with `fernz[textual]==0.0.1` to verify the frontend extra.
   `--help` does not download games. Use only legitimately obtained stories for
   interactive play; ROMs are intentionally absent from the package.
5. For a newly created project, verify the pending PyPI publisher has converted
   to a regular `fernz` publisher and Adam has the expected project ownership.
   Verify these through the account UI; never expose tokens or OIDC responses in
   issue comments or logs.

## 7. Diagnose failures and retry safely

| Symptom | Diagnosis and response |
| --- | --- |
| No release run | Confirm a single `v*` tag was pushed to `afourney/fernz`, the tagged commit includes `release.yml`, Actions are enabled, and the push was not made with a workflow `GITHUB_TOKEN`. A branch push or Release UI action alone is not the configured trigger. |
| Publish skipped | Check build success and the repository, push event and tag ref against the publish condition. Publication is restricted to `afourney/fernz`. |
| Waiting for approval | Review the `pypi` deployment. Check reviewer availability and self-review settings; do not remove protection just to bypass a failed build. |
| Environment rejects ref | Confirm the environment allows **Tag** `v*`, not only Branch `main` or a similarly named branch rule. |
| Version mismatch | The tagged commit's `pyproject.toml` must match literally. Inspect the tag target, not current main. Prepare a corrected version/commit through review. |
| Lock or artifact checks fail | Regenerate/review the lockfile or repair packaging, and inspect the specific assertion. Keep exactly one wheel and sdist in a fresh `dist/`; retain the no-ROM and dependency checks. |
| Twine metadata error | Fix the reported README/metadata problem in source and rebuild. Do not turn off strict validation. |
| OIDC unavailable | Confirm the publish job retains `id-token: write` and runs on supported GitHub-hosted Linux, and that account policies allow the action. Do not add a password as a workaround. |
| `invalid-publisher` or identity mismatch | Compare PyPI's saved owner, repository, `release.yml` filename and `pypi` environment with the table above; distinguish PyPI from TestPyPI. See the PyPI troubleshooting link below. |
| Project name rejected / access denied | Check existing ownership, pending publisher status and name availability. GitHub access cannot grant rights to another user's PyPI project. |
| Artifact not found | Check the same run's build success and `dist` artifact retention. The publish job downloads only that run's artifact. Never substitute an artifact from another commit/run. |
| File already exists / partial upload | Stop and inspect PyPI files and digests before retrying; see the limits below. A failed job does not prove that nothing was uploaded. |
| PyPI timeout / service error | Inspect the run logs and PyPI release files first. A lost success response may occur after upload. Check service status; retry only after determining which files, if any, exist. |

**Retry limits:** If no files were uploaded, and the defect was only external
configuration or a transient service failure, fix that cause and rerun the failed
publish job from the original tag run while its validated artifact still exists.
A rerun uses the original ref/commit; editing `release.yml` on main will not change
that old run. Never use a new tag push or a force-moved tag as a blind retry.

If both files already exist and their hashes match the run artifact, treat the
upload as complete and investigate any subsequent status/attestation failure;
do not upload them again. If only one file exists, this workflow intentionally
fails on duplicates and is **not** an automatic partial-release repair mechanism.
A maintainer must decide on a separately reviewed recovery of only the missing,
original validated file, or issue a corrected new version. Do not enable
`skip-existing` to conceal a mismatch. If any uploaded bytes are wrong, publish a
new version; consider yanking the bad release to discourage new installations.
Do not delete files expecting to reuse the names: PyPI does not permit filename
reuse even after deletion. Do not rebuild expired artifacts and assume they are
byte-identical; use a new version unless a deliberate recovery has been verified.

Never rewrite a published tag. Even before upload, prefer a fresh reviewed
version/tag over moving a public release tag. A new version requires updating
both `pyproject.toml` and `uv.lock`, passing checks, and a new matching tag. Reruns
can contact production PyPI and require the same care and authorization as the
original release.

## Official references

The workflow and this guide were checked against the following documentation:

- [PyPA publish action: permissions, artifacts, attestations and duplicate behavior](https://github.com/pypa/gh-action-pypi-publish)
- [PyPI Trusted Publisher troubleshooting](https://docs.pypi.org/trusted-publishers/troubleshooting/)
- [PyPI filename reuse restrictions](https://pypi.org/help/#file-name-reuse)
- [PyPI yanking releases](https://docs.pypi.org/project-management/yanking/)
- [GitHub push/tag events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [GitHub upload-artifact](https://github.com/actions/upload-artifact)
- [GitHub download-artifact](https://github.com/actions/download-artifact)
- [uv package build guidance](https://docs.astral.sh/uv/guides/package/)

Account setup and release operations above are maintainer actions. A PR adding
this workflow does not configure permissions, create tags, publish distributions,
or merge itself.
