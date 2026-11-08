import server
import unittest
import time
from pathlib import Path
from unittest.mock import patch
from server import Handler, chat, HISTORIES, LOCK
import skills_engine


class TestSkillsSystem(unittest.TestCase):
    def setUp(self):
        with LOCK:
            HISTORIES["developer"].clear()
            HISTORIES["cyber"].clear()

    def tearDown(self):
        with LOCK:
            HISTORIES["developer"].clear()
            HISTORIES["cyber"].clear()

    def test_all_skills_parse_cleanly(self):
        """Every skill file must parse with valid non-empty fields matching its filename."""
        dev_dir = skills_engine.SKILLS_DIR / "developer"
        cyber_dir = skills_engine.SKILLS_DIR / "cyber"

        all_files = list(dev_dir.glob("*.md")) + list(cyber_dir.glob("*.md"))
        self.assertEqual(len(all_files), 36, "Expected exactly 36 skill files (18 dev, 18 cyber).")

        for f in all_files:
            skill = skills_engine.parse_skill_file(f)
            self.assertEqual(skill.name, f.stem, f"Skill name '{skill.name}' must match file stem '{f.stem}'.")
            self.assertTrue(len(skill.description) > 5, f"Skill '{skill.name}' must have a valid description.")
            self.assertTrue(len(skill.triggers) >= 1, f"Skill '{skill.name}' must have at least one trigger.")
            self.assertTrue(len(skill.content.strip()) > 50, f"Skill '{skill.name}' content is too short.")

            # If it's one of the 20 new skills, verify standard section headers
            new_dev_skills = {
                "architecture-design", "api-design", "database-design", "performance-profiling",
                "security-hardening", "error-handling-logging", "test-strategy", "documentation-writer",
                "legacy-code-explainer", "voice-ux-design"
            }
            new_cyber_skills = {
                "threat-modeling", "log-analysis-detection", "malware-analysis-concepts",
                "web-app-security-review", "cloud-security-basics", "digital-forensics",
                "vuln-management", "secure-architecture", "security-reporting", "security-awareness"
            }
            if skill.name in (new_dev_skills | new_cyber_skills):
                self.assertIn("## When to use", skill.content, f"{skill.name} missing '## When to use'")
                self.assertIn("## Procedure", skill.content, f"{skill.name} missing '## Procedure'")
                self.assertIn("## Checklist", skill.content, f"{skill.name} missing '## Checklist'")
                self.assertIn("## Output format", skill.content, f"{skill.name} missing '## Output format'")
                self.assertIn("## Example", skill.content, f"{skill.name} missing '## Example'")

    def test_mode_skills_are_strictly_isolated(self):
        """Developer mode never loads cyber skills, and cyber mode never loads developer skills."""
        dev_skills = skills_engine.load_skills("developer")
        cyber_skills = skills_engine.load_skills("cyber")

        self.assertEqual(len(dev_skills), 18)
        self.assertEqual(len(cyber_skills), 18)

        dev_names = {s.name for s in dev_skills}
        cyber_names = {s.name for s in cyber_skills}

        # Sets must be completely disjoint
        self.assertTrue(dev_names.isdisjoint(cyber_names))

        # Check existing 8 developer skills
        existing_dev = {
            "plan-before-code", "tdd", "systematic-debugging", "code-review",
            "verify-before-done", "small-commits", "refactor-safely", "project-conventions"
        }
        self.assertTrue(existing_dev.issubset(dev_names))

        # Check existing 8 cyber skills
        existing_cyber = {
            "secure-code-review", "vulnerability-analysis", "threat-intel-summary",
            "incident-response", "network-defense", "ctf-practice",
            "osint-methodology", "authorized-pentest-methodology"
        }
        self.assertTrue(existing_cyber.issubset(cyber_names))

    def test_cyber_guardrail_present_in_all_cyber_skills(self):
        """Every cyber skill must contain the defensive and authorized use guardrail."""
        cyber_skills = skills_engine.load_skills("cyber")
        guardrail_snippet = "Defensive, educational, and authorized use only"
        for skill in cyber_skills:
            self.assertIn(
                guardrail_snippet.lower(),
                skill.content.lower(),
                f"Skill '{skill.name}' is missing the required cyber guardrail."
            )

    def test_20_new_skills_selection(self):
        """For each of the 20 new skills, verify a dedicated sample message selects it as top-2."""
        # 10 Developer Skills
        dev_test_cases = [
            ("architecture-design", "We need an architecture design and data flow design for the new engine"),
            ("api-design", "Help me with the rest api endpoint design and schemas"),
            ("database-design", "Plan the sqlite design and database migration schema for our tables"),
            ("performance-profiling", "Run performance profiling and benchmark with cprofile to find the hotspot"),
            ("security-hardening", "Apply security hardening and localhost binding to secure endpoints"),
            ("error-handling-logging", "Design error handling and structured logging with retry backoff"),
            ("test-strategy", "Define our test strategy and test plan for integration tests"),
            ("documentation-writer", "Act as documentation writer to write docs and update readme"),
            ("legacy-code-explainer", "Explain this legacy code and trace request through codebase"),
            ("voice-ux-design", "Design the voice ux and conversational ux for speakable reply"),
        ]

        for skill_slug, sample_msg in dev_test_cases:
            matches = skills_engine.select_skills("developer", sample_msg, limit=2)
            match_names = [s.name for s in matches]
            self.assertIn(
                skill_slug,
                match_names,
                f"Expected '{skill_slug}' in top-2 developer skills for '{sample_msg}', got {match_names}"
            )

        # 10 Cyber Skills
        cyber_test_cases = [
            ("threat-modeling", "Perform threat modeling using stride and trust boundaries"),
            ("log-analysis-detection", "Do log analysis and detection engineering to write a sigma rule"),
            ("malware-analysis-concepts", "Explain malware analysis concepts and write a yara rule in malware lab"),
            ("web-app-security-review", "Conduct a web app security review against owasp top 10"),
            ("cloud-security-basics", "Audit our cloud security posture and iam least privilege in aws security"),
            ("digital-forensics", "Follow digital forensics procedures for evidence preservation and artifact analysis"),
            ("vuln-management", "Set up vulnerability management and vuln scan tracking with cvss scoring"),
            ("secure-architecture", "Design a secure architecture with zero trust and defense in depth"),
            ("security-reporting", "Draft an executive summary security report and audit report"),
            ("security-awareness", "Create security awareness training for phishing training and password hygiene"),
        ]

        for skill_slug, sample_msg in cyber_test_cases:
            matches = skills_engine.select_skills("cyber", sample_msg, limit=2)
            match_names = [s.name for s in matches]
            self.assertIn(
                skill_slug,
                match_names,
                f"Expected '{skill_slug}' in top-2 cyber skills for '{sample_msg}', got {match_names}"
            )

    def test_multilingual_skill_selection(self):
        """Verify Bengali queries match the appropriate skills."""
        res_bn_dev = skills_engine.select_skills("developer", "আমার কোডে একটা বাগ আছে, ফিক্স করতে সাহায্য করো")
        self.assertTrue(any(s.name == "systematic-debugging" for s in res_bn_dev))

        res_bn_plan = skills_engine.select_skills("developer", "নতুন ফিচারের জন্য একটা পরিকল্পনা করো")
        self.assertTrue(any(s.name == "plan-before-code" for s in res_bn_plan))

        res_bn_arch = skills_engine.select_skills("developer", "সিস্টেমের আর্কিটেকচার নকশা তৈরি করো")
        self.assertTrue(any(s.name == "architecture-design" for s in res_bn_arch))

        res_bn_cyber = skills_engine.select_skills("cyber", "এই অ্যাপ্লিকেশনের সিকিউরিটি ও কোড রিভিউ করো")
        self.assertTrue(any(s.name == "secure-code-review" for s in res_bn_cyber))

        res_bn_aware = skills_engine.select_skills("cyber", "কর্মীদের জন্য সিকিউরিটি সচেতনতা এবং ফিশিং ট্রেনিং তৈরি করো")
        self.assertTrue(any(s.name == "security-awareness" for s in res_bn_aware))

    def test_empty_or_unmatched_returns_empty(self):
        """Empty or unmatched messages return empty list and empty prompt."""
        self.assertEqual(skills_engine.select_skills("developer", ""), [])
        self.assertEqual(skills_engine.select_skills("developer", "   "), [])
        self.assertEqual(skills_engine.build_skill_prompt("developer", ""), "")

        unrelated = "Good morning, how are you today?"
        self.assertEqual(skills_engine.select_skills("developer", unrelated), [])
        self.assertEqual(skills_engine.build_skill_prompt("developer", unrelated), "")

    def test_api_skills_endpoint_and_local_protection(self):
        """GET /api/skills returns 18 skills per mode and rejects non-local origins."""
        class MockRequest:
            def __init__(self, path, host="127.0.0.1:8765", origin=None):
                self.path = path
                self.headers = {"Host": host, "Cookie": f"nova_session={server.SESSION_TOKEN}", "X-Nova-Token": server.API_SESSION_TOKEN}
                if origin:
                    self.headers["Origin"] = origin
                self.status = None
                self.data = None

            _local_only = Handler._local_only
            do_GET = Handler.do_GET

            def _send(self, status, data, ctype="application/json"):
                self.status = status
                self.data = data

        # Test local allowed request for developer mode (18 skills)
        req_dev = MockRequest("/api/skills?mode=developer")
        req_dev.do_GET()
        self.assertEqual(req_dev.status, 200)
        self.assertEqual(req_dev.data["mode"], "developer")
        self.assertEqual(len(req_dev.data["skills"]), 18)
        dev_names = [s["name"] for s in req_dev.data["skills"]]
        self.assertIn("architecture-design", dev_names)
        self.assertIn("systematic-debugging", dev_names)
        self.assertNotIn("threat-modeling", dev_names)

        # Test local allowed request for cyber mode (18 skills)
        req_cyber = MockRequest("/api/skills?mode=cyber")
        req_cyber.do_GET()
        self.assertEqual(req_cyber.status, 200)
        self.assertEqual(req_cyber.data["mode"], "cyber")
        self.assertEqual(len(req_cyber.data["skills"]), 18)
        cyber_names = [s["name"] for s in req_cyber.data["skills"]]
        self.assertIn("threat-modeling", cyber_names)
        self.assertIn("secure-code-review", cyber_names)
        self.assertNotIn("architecture-design", cyber_names)

        # Test rejection of non-local Host (DNS rebinding / remote access)
        req_remote = MockRequest("/api/skills?mode=developer", host="attacker.com:8765")
        req_remote.do_GET()
        self.assertEqual(req_remote.status, 403)

        # Test rejection of malicious Origin
        req_bad_origin = MockRequest("/api/skills?mode=developer", host="127.0.0.1:8765", origin="http://evil.com")
        req_bad_origin.do_GET()
        self.assertEqual(req_bad_origin.status, 403)

    def test_histories_isolation_remains_intact(self):
        """Histories remain strictly isolated when skills are injected via real server.chat."""
        with patch("server.call_llm", side_effect=["Fix bug reply", "Review CVE reply"]):
            chat("Fix bug in dev", mode="developer")
            chat("Review CVE in cyber", mode="cyber")

        self.assertEqual(len(HISTORIES["developer"]), 2)
        self.assertEqual(len(HISTORIES["cyber"]), 2)
        self.assertEqual(HISTORIES["developer"][0]["content"], "Fix bug in dev")
        self.assertEqual(HISTORIES["cyber"][0]["content"], "Review CVE in cyber")


if __name__ == "__main__":
    unittest.main()
