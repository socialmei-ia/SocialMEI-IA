from pathlib import Path
import re
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = ROOT / ".codex" / "agents"
SKILLS_DIR = ROOT / ".agents" / "skills"
CONFIG_PATH = ROOT / ".codex" / "config.toml"


class CodexConfigurationTests(unittest.TestCase):
    def test_project_config_is_valid_toml(self):
        data = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        agents = data.get("agents", {})

        self.assertTrue(agents.get("enabled"))
        self.assertGreaterEqual(agents.get("max_concurrent_threads_per_session", 0), 1)
        self.assertLessEqual(agents.get("max_concurrent_threads_per_session", 0), 3)

    def test_agent_files_are_valid_and_unique(self):
        paths = sorted(AGENTS_DIR.glob("*.toml"))
        self.assertGreaterEqual(len(paths), 20)

        names = set()
        valid_efforts = {"low", "medium", "high", "xhigh", "extra_high"}
        valid_sandboxes = {"read-only", "workspace-write", "danger-full-access"}

        for path in paths:
            with self.subTest(path=path.name):
                data = tomllib.loads(path.read_text(encoding="utf-8"))

                name = data.get("name", "").strip()
                description = data.get("description", "").strip()
                instructions = data.get("developer_instructions", "").strip()

                self.assertTrue(name)
                self.assertEqual(name, path.stem)
                self.assertNotIn(name, names)
                self.assertTrue(description)
                self.assertTrue(instructions)

                effort = data.get("model_reasoning_effort")
                if effort is not None:
                    self.assertIn(effort, valid_efforts)

                sandbox = data.get("sandbox_mode")
                if sandbox is not None:
                    self.assertIn(sandbox, valid_sandboxes)

                names.add(name)

    def test_skill_frontmatter_is_present_and_matches_folder(self):
        paths = sorted(SKILLS_DIR.glob("*/SKILL.md"))
        self.assertGreaterEqual(len(paths), 9)

        names = set()
        for path in paths:
            with self.subTest(path=str(path.relative_to(ROOT))):
                text = path.read_text(encoding="utf-8")
                match = re.match(
                    r"^---\n(?P<header>.*?)\n---\n",
                    text,
                    flags=re.DOTALL,
                )
                self.assertIsNotNone(match)

                header = match.group("header")
                name_match = re.search(r"^name:\s*(.+?)\s*$", header, flags=re.MULTILINE)
                description_match = re.search(
                    r"^description:\s*(.+?)\s*$",
                    header,
                    flags=re.MULTILINE,
                )

                self.assertIsNotNone(name_match)
                self.assertIsNotNone(description_match)

                name = name_match.group(1).strip()
                description = description_match.group(1).strip()

                self.assertEqual(name, path.parent.name)
                self.assertNotIn(name, names)
                self.assertTrue(description)
                names.add(name)


if __name__ == "__main__":
    unittest.main()
