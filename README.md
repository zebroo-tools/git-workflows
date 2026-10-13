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
    uses: Odoo-Ninjas/git-workflows/.github/workflows/robotests.yml@v9
    with:
      enabled: true
      projectname: myproject

  run_unit_tests:
    uses: Odoo-Ninjas/git-workflows/.github/workflows/unittests.yml@v9
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
    uses: Odoo-Ninjas/git-workflows/.github/workflows/deploy_to_subversions.yml@v9
    with:
      branches: <mappings>
    secrets:
      SSH_PRIVATE_KEY:  ${{ secrets.SSH_PRIVATE_KEY }}


```