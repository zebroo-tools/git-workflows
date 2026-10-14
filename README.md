# Setup Robotests/Unittests for odoo projects

*  create .github/workflows/testing.yml

```yaml

name: testing
on:
  push:
    branches-ignore:

permissions: write-all

jobs:
  run_robo_tests:
    uses: zebroo-tools/git-workflows/.github/workflows/robotests.yml@v9
    with:
      enabled: true
      projectname: myproject

  run_unit_tests:
    uses: zebroo-tools/git-workflows/.github/workflows/unittests.yml@v9
    with:
      enabled: true
      projectname: myproject

```

# Deploy to subversions (tip: use odoo-version-manager)

```yaml

name: Deploy fixes to other versions with rebase main

on:
  push:
    branches:
      - <current_branch>

permissions: write-all

jobs:
  deploy-subversions:
    uses: zebroo-tools/git-workflows/.github/workflows/deploy_to_subversions.yml@v9
    with:
      branches: <mappings>
    secrets:
      SSH_PRIVATE_KEY:  ${{ secrets.SSH_PRIVATE_KEY }}


```

## Reviewed version integration

The subversion workflow prepares merge PRs instead of rebasing and force-pushing
shared version branches. `branches` retains its `destination:source` mappings
and `|||` groups. A conflict, failed fetch or rejected push fails the job;
independent groups still run. Destination branches are never written directly.
An already integrated source needs no PR. Integration branches are identified
by source commit; repeated runs reuse an open PR when both input histories are
still included. A changed destination requires a newly reviewed resolution.

Callers need `contents: write`, `pull-requests: write` and `issues: write`.
The repository must allow GitHub Actions to create pull requests. The existing
SSH key is used only for normal integration-branch pushes. Review and target
version tests remain required before merging; no production database rollout
is performed by this workflow.
