# Part of Zebroo GmbH. See LICENSE file for full copyright and licensing details (www.zebroo.de/license).
"""Exercise the embedded workflow scripts against isolated Git repositories."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

WORKFLOW = Path(
    os.environ.get(
        "WORKFLOW_OVERRIDE",
        str(Path(__file__).parents[1] / ".github/workflows/deploy_to_subversions.yml"),
    )
)


def run(*args, cwd=None, env=None, check=True):
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.remote = self.root / "remote.git"
        self.repo = self.root / "repo"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.calls = self.root / "gh-calls"
        (self.bin / "gh").write_text(
            '#!/bin/bash\nprintf "%s\\n" "$*" >> "$GH_CALLS"\nif [[ "$1 $2" == "pr list" ]]; then echo 0; fi\n'
            'if [[ "$1 $2" == "issue list" ]]; then printf "%s" "${GH_OPEN_ISSUES:-}"; fi\n'
        )
        (self.bin / "gh").chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
            "GH_CALLS": str(self.calls),
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        run("git", "init", "--bare", str(self.remote))
        run("git", "clone", str(self.remote), str(self.repo))
        self.git("config", "user.name", "Integration test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("checkout", "-b", "source")
        self.commit("base.txt", "base")
        self.git("checkout", "-b", "dest")
        self.commit("dest.txt", "destination only")
        self.git("checkout", "source")
        self.commit("source.txt", "source only")
        self.git("push", "--set-upstream", "origin", "source", "dest")
        self.before = run(
            "git", "--git-dir", str(self.remote), "rev-parse", "dest"
        ).stdout.strip()
        self.steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["build"]["steps"]
        self.prepare = next(
            s["run"]
            for s in self.steps
            if s.get("name", "")
            in {"Prepare integration script", "prepare rebase script"}
        )
        self.body = (
            self.prepare.split("cat <<'EOF' > /tmp/", 1)[1]
            .split("\n", 1)[1]
            .rsplit("\nEOF", 1)[0]
        )
        self.script = self.root / "integrate.sh"
        self.script.write_text(self.body)

    def gh_calls(self):
        return self.calls.read_text() if self.calls.exists() else ""

    def git(self, *args, check=True):
        return run("git", *args, cwd=self.repo, env=self.env, check=check)

    def commit(self, name, value):
        (self.repo / name).write_text(value + "\n")
        self.git("add", name)
        self.git("commit", "-m", "test change")

    def integrate(self, source="source", dest="dest"):
        return run(
            "bash",
            str(self.script),
            source,
            dest,
            cwd=self.repo,
            env=self.env,
            check=False,
        )

    def remote_dest(self):
        return run(
            "git", "--git-dir", str(self.remote), "rev-parse", "dest"
        ).stdout.strip()

    def test_divergent_histories_make_pr_without_touching_destination(self):
        result = self.integrate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.remote_dest(), self.before)
        self.assertIn("pr create", self.calls.read_text())
        for ref in ["origin/source", "origin/dest"]:
            self.assertEqual(
                self.git(
                    "merge-base", "--is-ancestor", ref, "HEAD", check=False
                ).returncode,
                0,
            )
        self.assertTrue((self.repo / "dest.txt").exists())
        self.assertTrue((self.repo / "source.txt").exists())

    def test_conflict_fails_without_changing_destination(self):
        self.commit("base.txt", "source change")
        self.git("checkout", "dest")
        self.commit("base.txt", "destination change")
        self.git("push", "--set-upstream", "origin", "source", "dest")
        before = self.remote_dest()
        result = self.integrate()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.remote_dest(), before)
        self.assertIn("issue create", self.calls.read_text())
        self.assertNotIn("pr create", self.calls.read_text())
        self.assertFalse((self.repo / ".git/MERGE_HEAD").exists())

    def test_rejected_push_fails_without_pr(self):
        hook = self.remote / "hooks/pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        result = self.integrate()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.remote_dest(), self.before)
        self.assertNotIn("create", self.gh_calls())

    def test_integrated_source_is_noop(self):
        self.git("checkout", "dest")
        self.git("merge", "--no-edit", "source")
        self.git("push", "origin", "dest")
        before = self.remote_dest()
        self.assertEqual(self.integrate().returncode, 0)
        self.assertEqual(self.remote_dest(), before)
        self.assertNotIn("create", self.gh_calls())

    def make_conflict(self):
        self.commit("base.txt", "source change")
        self.git("checkout", "dest")
        self.commit("base.txt", "destination change")
        self.git("push", "--set-upstream", "origin", "source", "dest")

    def test_conflict_comments_on_open_issue_instead_of_creating_one(self):
        self.make_conflict()
        self.env["GH_OPEN_ISSUES"] = "42"
        self.assertNotEqual(self.integrate().returncode, 0)
        self.assertIn("issue comment 42", self.gh_calls())
        self.assertNotIn("issue create", self.gh_calls())

    def test_clean_merge_closes_open_conflict_issue(self):
        self.env["GH_OPEN_ISSUES"] = "42"
        self.assertEqual(self.integrate().returncode, 0)
        self.assertIn("issue close 42", self.gh_calls())

    def test_integrated_source_closes_open_conflict_issue(self):
        self.git("checkout", "dest")
        self.git("merge", "--no-edit", "source")
        self.git("push", "origin", "dest")
        self.env["GH_OPEN_ISSUES"] = "42"
        self.assertEqual(self.integrate().returncode, 0)
        self.assertIn("issue close 42", self.gh_calls())

    def test_changed_destination_does_not_overwrite_existing_branch(self):
        self.assertEqual(self.integrate().returncode, 0)
        self.git("checkout", "dest")
        self.commit("later.txt", "later destination change")
        self.git("push", "origin", "dest")
        before = self.remote_dest()
        self.assertNotEqual(self.integrate().returncode, 0)
        self.assertEqual(self.remote_dest(), before)

    def test_failure_in_first_group_is_not_erased_by_later_group(self):
        body = next(
            s["run"]
            for s in self.steps
            if s.get("name", "").startswith("Prepare integration PRs;")
        )
        body = body.replace("/tmp/integrate.sh", str(self.script))
        result = run(
            "bash",
            "-c",
            body,
            cwd=self.repo,
            env={**self.env, "BRANCH_MAPPINGS": "dest:missing ||| dest:source"},
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.remote_dest(), self.before)
        self.assertIn("pr create", self.calls.read_text())

    def test_invalid_mapping_fails(self):
        body = next(
            s["run"]
            for s in self.steps
            if s.get("name", "").startswith("Prepare integration PRs;")
        )
        result = run(
            "bash",
            "-c",
            body,
            cwd=self.repo,
            env={**self.env, "BRANCH_MAPPINGS": "invalid"},
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.remote_dest(), self.before)


if __name__ == "__main__":
    unittest.main()
