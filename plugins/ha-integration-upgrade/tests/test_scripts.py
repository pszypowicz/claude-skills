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
    """A remote with dev history, two release branches, and their tags."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="fetch-core-")
        cls.remote = os.path.join(cls.root, "remote")
        cls.env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                       GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.invalid",
                       GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.invalid")
        cls.git("init", "-q", "-b", "dev", cls.remote)
        cls.git("-C", cls.remote, "config", "uploadpack.allowFilter", "true")
        cls.commit("2026-09-01", "Old dev work")
        cls.commit("2026-09-30", "Cut 2026.10", tag="2026.10.0b0")
        cls.git("-C", cls.remote, "checkout", "-q", "-b", "rc-2026.10")
        cls.commit("2026-10-07", "2026.10.0", tag="2026.10.0")
        cls.git("-C", cls.remote, "checkout", "-q", "dev")
        cls.commit("2026-10-15", "Add a helper (#2)")
        cls.commit("2026-10-28", "Cut 2026.11", tag="2026.11.0b0")
        cls.commit("2026-11-04", "2026.11.0", tag="2026.11.0")

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

    def fetch(self, *args):
        cache = tempfile.mkdtemp(prefix="cache-", dir=self.root)
        return run(FETCH_CORE, "--cache-dir", cache, "--remote", f"file://{self.remote}", *args, env=self.env), cache

    def test_two_releases(self):
        result, cache = self.fetch("--from", "2026.10", "--to", "2026.11")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0], f"repo: {cache}")
        dates = [line.split()[-1] for line in lines if line.startswith("tag: ")]
        self.assertEqual(dates, ["2026-09-30", "2026-10-07", "2026-10-28", "2026-11-04"])
        self.assertIn("commits: 3 in 2026.10.0..2026.11.0", lines)
        self.assertEqual(lines[-1], "blog-window: 2026-09-23 2026-11-18")
        log = self.git("-C", cache, "log", "--format=%s", "2026.10.0..2026.11.0")
        self.assertEqual(log.splitlines(), ["2026.11.0", "Cut 2026.11", "Add a helper (#2)"])

    def test_a_second_run_reuses_the_cache(self):
        _, cache = self.fetch("--from", "2026.10", "--to", "2026.11")
        again = run(FETCH_CORE, "--cache-dir", cache, "--remote", f"file://{self.remote}",
                    "--from", "2026.10.0", "--to", "2026.11.0", env=self.env)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("commits: 3 in 2026.10.0..2026.11.0", again.stdout.splitlines())

    def test_an_unreleased_target(self):
        result, _ = self.fetch("--from", "2026.11", "--to", "2026.12")
        self.assertEqual(result.returncode, 1)
        self.assertIn("is 2026.12.0 released?", result.stderr)

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


if __name__ == "__main__":
    unittest.main()
