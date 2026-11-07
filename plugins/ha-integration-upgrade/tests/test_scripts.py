"""Offline tests for the bundled scripts: feeds and a core remote on disk."""

import os
import shutil
import subprocess
import tempfile
import unittest

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(PLUGIN, "skills", "ha-integration-upgrade", "scripts")
BLOG_POSTS = os.path.join(SCRIPTS, "blog-posts.sh")
FETCH_CORE = os.path.join(SCRIPTS, "fetch-core.sh")
FRONTEND_RELEASES = os.path.join(SCRIPTS, "frontend-releases.sh")
GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
               GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.invalid",
               GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.invalid")


def run(*args, env=None):
    return subprocess.run(list(args), capture_output=True, text=True, env=env)


def rss(*items):
    body = "".join(
        f"<item><title>{title}</title><link>{link}</link>"
        f"<description>{description}</description><pubDate>{date}</pubDate></item>"
        for title, link, description, date in items
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>{body}</channel></rss>'


class TestBlogPosts(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="blog-posts-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        shared = ("Categories", "https://blog.example/c/", "Shared  post\n desc", "Tue, 20 Oct 2026 00:00:00 GMT")
        self.write_feed("core", rss(
            ("Too early", "https://blog.example/a/", "a", "Mon, 21 Sep 2026 00:00:00 GMT"),
            ("Later", "https://blog.example/d/", "d", "Fri, 23 Oct 2026 00:00:00 GMT"),
            shared,
            ("Too late", "https://blog.example/z/", "z", "Mon, 30 Nov 2026 00:00:00 GMT"),
        ))
        self.write_feed("marketplace", rss(shared))

    def write_feed(self, area, text):
        os.makedirs(os.path.join(self.root, area))
        with open(os.path.join(self.root, area, "rss.xml"), "w") as f:
            f.write(text)

    def posts(self, *extra):
        return run(BLOG_POSTS, "--since", "2026-09-23", "--until", "2026-11-18",
                   "--feed-base", f"file://{self.root}", *extra)

    def test_window_order_and_merged_areas(self):
        result = self.posts()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            "2026-10-20\tcore,marketplace\tCategories\thttps://blog.example/c/\tShared post desc",
            "2026-10-23\tcore\tLater\thttps://blog.example/d/\td",
        ])

    def test_a_single_area(self):
        result = self.posts("--area", "marketplace")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([line.split("\t")[2] for line in result.stdout.splitlines()], ["Categories"])

    def test_a_missing_feed_prints_no_posts(self):
        result = self.posts("--area", "core", "--area", "absent")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("absent/rss.xml", result.stderr)

    def test_required_flags(self):
        result = run(BLOG_POSTS, "--since", "2026-09-23")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--until is required", result.stderr)

    def test_a_bad_date(self):
        result = run(BLOG_POSTS, "--since", "23.09.2026", "--until", "2026-11-18")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not a YYYY-MM-DD date", result.stderr)


class TestFetchCore(unittest.TestCase):
    """A remote with dev history, three release branches, and their tags."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="fetch-core-")
        cls.remote = os.path.join(cls.root, "remote")
        cls.env = GIT_ENV
        cls.git("init", "-q", "-b", "dev", cls.remote)
        cls.git("-C", cls.remote, "config", "uploadpack.allowFilter", "true")
        cls.commit("2026-07-01", "Old dev work")
        cls.release("2026.9", cut="2026-08-26", ship="2026-09-02")
        cls.commit("2026-09-10", "Add a helper (#2)")
        cls.release("2026.10", cut="2026-09-30", ship="2026-10-07")
        cls.commit("2026-10-15", "Add another helper (#3)")
        cls.release("2026.11", cut="2026-10-28", ship="2026-11-04")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    @classmethod
    def git(cls, *args, date=None):
        env = dict(cls.env)
        if date:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"{date}T12:00:00Z"
        result = subprocess.run(["git", *args], capture_output=True, text=True, env=env)
        assert result.returncode == 0, result.stderr
        return result.stdout

    @classmethod
    def commit(cls, date, message, tag=None):
        path = os.path.join(cls.remote, "history.txt")
        with open(path, "a") as f:
            f.write(message + "\n")
        cls.git("-C", cls.remote, "add", "history.txt")
        cls.git("-C", cls.remote, "commit", "-q", "-m", message, date=date)
        if tag:
            cls.git("-C", cls.remote, "tag", tag)

    @classmethod
    def release(cls, minor, cut, ship):
        """Cut the first beta on dev, and ship the release from its own branch."""
        cls.commit(cut, f"Cut {minor}", tag=f"{minor}.0b0")
        cls.git("-C", cls.remote, "checkout", "-q", "-b", f"rc-{minor}")
        cls.commit(ship, f"{minor}.0", tag=f"{minor}.0")
        cls.git("-C", cls.remote, "checkout", "-q", "dev")

    def new_cache(self):
        return tempfile.mkdtemp(prefix="cache-", dir=self.root)

    def fetch(self, cache, *args):
        return run(FETCH_CORE, "--cache-dir", cache, "--remote", f"file://{self.remote}", *args, env=self.env)

    def count(self, cache, revisions):
        return int(self.git("-C", cache, "rev-list", "--count", revisions))

    def test_one_step(self):
        cache = self.new_cache()
        result = self.fetch(cache, "--from", "2026.10", "--to", "2026.11")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0], f"repo: {cache}")
        dates = [line.split()[-1] for line in lines if line.startswith("tag: ")]
        self.assertEqual(dates, ["2026-09-30", "2026-10-07", "2026-10-28", "2026-11-04"])
        self.assertEqual(lines[-1], "step: 2026.10.0..2026.11.0 commits: 3 blog-window: 2026-09-23 2026-11-18")
        log = self.git("-C", cache, "log", "--format=%s", "2026.10.0..2026.11.0")
        self.assertEqual(log.splitlines(), ["2026.11.0", "Cut 2026.11", "Add another helper (#3)"])

    def test_a_chain_of_steps(self):
        cache = self.new_cache()
        result = self.fetch(cache, "--from", "2026.9", "--to", "2026.11")
        self.assertEqual(result.returncode, 0, result.stderr)
        steps = [line for line in result.stdout.splitlines() if line.startswith("step: ")]
        self.assertEqual(steps, [
            "step: 2026.9.0..2026.10.0 commits: 3 blog-window: 2026-08-19 2026-10-21",
            "step: 2026.10.0..2026.11.0 commits: 3 blog-window: 2026-09-23 2026-11-18",
        ])

    def test_a_later_step_keeps_the_history_of_an_earlier_one(self):
        cache = self.new_cache()
        self.assertEqual(self.fetch(cache, "--from", "2026.9", "--to", "2026.10").returncode, 0)
        before = self.count(cache, "2026.9.0..2026.10.0")
        result = self.fetch(cache, "--from", "2026.10", "--to", "2026.11")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.git("-C", cache, "merge-base", "2026.9.0", "2026.10.0")
        self.assertEqual(self.count(cache, "2026.9.0..2026.10.0"), before)

    def test_a_second_run_reuses_the_cache(self):
        cache = self.new_cache()
        self.fetch(cache, "--from", "2026.10", "--to", "2026.11")
        again = self.fetch(cache, "--from", "2026.10.0", "--to", "2026.11.0")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("step: 2026.10.0..2026.11.0 commits: 3 blog-window: 2026-09-23 2026-11-18",
                      again.stdout.splitlines())

    def test_an_unreleased_target(self):
        result = self.fetch(self.new_cache(), "--from", "2026.11", "--to", "2026.12")
        self.assertEqual(result.returncode, 1)
        self.assertIn("is 2026.12.0 released?", result.stderr)

    def test_a_target_before_the_source(self):
        result = self.fetch(self.new_cache(), "--from", "2026.11", "--to", "2026.10")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--to 2026.10.0 is not after --from 2026.11.0", result.stderr)

    def test_not_a_version(self):
        cache = os.path.join(self.root, "never-created")
        result = run(FETCH_CORE, "--cache-dir", cache, "--from", "latest", "--to", "2026.11")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not a Home Assistant version: latest", result.stderr)
        self.assertFalse(os.path.exists(cache))

    def test_required_flags(self):
        result = run(FETCH_CORE, "--to", "2026.11")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--from is required", result.stderr)


class TestFrontendReleases(unittest.TestCase):
    """Core tags that pin two frontend versions, and a gh that knows the releases."""

    RELEASES = ["20261028.10", "20261028.4", "20261028.0", "20260930.3", "20260930.2", "20260930.1"]

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="frontend-releases-")
        cls.cache = os.path.join(cls.root, "core")
        git = lambda *args: subprocess.run(["git", "-C", cls.cache, *args], check=True,
                                           capture_output=True, env=GIT_ENV)
        os.makedirs(os.path.join(cls.cache, "homeassistant", "components", "frontend"))
        subprocess.run(["git", "init", "-q", cls.cache], check=True, env=GIT_ENV)
        for tag, pin in (("2026.10.0", "20260930.2"), ("2026.11.0", "20261028.4"), ("2026.11.1", "20261028.4")):
            with open(os.path.join(cls.cache, "homeassistant", "components", "frontend", "manifest.json"), "w") as f:
                f.write('{"domain": "frontend", "requirements": ["home-assistant-frontend==%s"]}\n' % pin)
            git("add", "-A")
            git("commit", "-q", "--allow-empty", "-m", tag)
            git("tag", tag)
        cls.bin = os.path.join(cls.root, "bin")
        os.makedirs(cls.bin)
        gh = os.path.join(cls.bin, "gh")
        with open(gh, "w") as f:
            f.write("#!/usr/bin/env bash\n"
                    'case "$1 $2" in\n'
                    f'  "release list") printf \'%s\\n\' {" ".join(cls.RELEASES)} ;;\n'
                    '  "release view") printf \'* Change one of %s\\n* Change two\\n\' "$3" ;;\n'
                    '  *) echo "unexpected: $*" >&2; exit 2 ;;\n'
                    "esac\n")
        os.chmod(gh, 0o755)
        cls.env = dict(GIT_ENV, PATH=cls.bin + os.pathsep + os.environ["PATH"])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def releases(self, *args):
        return run(FRONTEND_RELEASES, "--cache-dir", self.cache, *args, env=self.env)

    def test_the_releases_a_step_brings_in(self):
        result = self.releases("--from", "2026.10.0", "--to", "2026.11.0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            "20260930.3\t* Change one of 20260930.3",
            "20260930.3\t* Change two",
            "20261028.0\t* Change one of 20261028.0",
            "20261028.0\t* Change two",
            "20261028.4\t* Change one of 20261028.4",
            "20261028.4\t* Change two",
        ])

    def test_an_unchanged_pin(self):
        result = self.releases("--from", "2026.11.0", "--to", "2026.11.1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("pins home-assistant-frontend 20261028.4 at both tags", result.stderr)

    def test_a_tag_missing_from_the_cache(self):
        result = self.releases("--from", "2026.9.0", "--to", "2026.10.0")
        self.assertEqual(result.returncode, 1)
        self.assertIn("2026.9.0", result.stderr)

    def test_required_flags(self):
        result = self.releases("--from", "2026.10.0")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--to is required", result.stderr)


if __name__ == "__main__":
    unittest.main()
