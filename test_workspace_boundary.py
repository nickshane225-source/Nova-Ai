"""
Unit tests for Workspace Path Boundary security enforcement.
"""
import unittest
import os
import sys
import platform
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server

class TestWorkspaceBoundary(unittest.TestCase):

    def setUp(self):
        self.workspace = server.WORKSPACE.resolve()
        self.test_sub_dir = self.workspace / "_boundary_test_dir"
        self.test_sub_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        if self.test_sub_dir.exists():
            import shutil
            shutil.rmtree(self.test_sub_dir, ignore_errors=True)

    def test_absolute_path_outside_rejected(self):
        outside_path = r"C:\Windows\System32\cmd.exe" if platform.system() == "Windows" else "/bin/bash"
        with self.assertRaises(PermissionError):
            server.resolve_workspace_path(outside_path)

        # WRITE_FILE tool returns clear error without touching file
        res = server.run_skill({}, "WRITE_FILE", f"{outside_path} | malicious payload")
        self.assertEqual(res, "Path is outside the Nova workspace.")

        # READ_FILE tool returns clear error
        res_read = server.run_skill({}, "READ_FILE", outside_path)
        self.assertEqual(res_read, "Path is outside the Nova workspace.")

    def test_dot_dot_escape_rejected(self):
        escape_path = "../../forbidden_escape.txt"
        with self.assertRaises(PermissionError):
            server.resolve_workspace_path(escape_path)

        res = server.run_skill({}, "WRITE_FILE", f"{escape_path} | escape attempt")
        self.assertEqual(res, "Path is outside the Nova workspace.")

        res_edit = server.run_skill({}, "EDIT_FILE", f"{escape_path} | old | new")
        self.assertEqual(res_edit, "Path is outside the Nova workspace.")

    def test_normal_relative_path_allowed(self):
        rel_file = "_boundary_test_dir/valid_file.txt"
        resolved = server.resolve_workspace_path(rel_file)
        self.assertTrue(resolved.is_relative_to(self.workspace))

        res = server.run_skill({}, "WRITE_FILE", f"{rel_file} | safe hello world")
        self.assertIn("Created file", res)
        self.assertTrue(resolved.exists())
        self.assertEqual(resolved.read_text(encoding="utf-8"), "safe hello world")

        # EDIT_FILE works
        edit_res = server.run_skill({}, "EDIT_FILE", f"{rel_file} | safe hello world | updated safe text")
        self.assertIn("Successfully edited", edit_res)
        self.assertEqual(resolved.read_text(encoding="utf-8"), "updated safe text")

        # READ_FILE works
        read_res = server.run_skill({}, "READ_FILE", rel_file)
        self.assertIn("updated safe text", read_res)

    def test_symlink_pointing_outside_rejected(self):
        # Create a temp file outside workspace
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"secret external data")
            tmp_path = Path(tmp.name).resolve()

        symlink_path = self.test_sub_dir / "symlink_to_external.txt"
        try:
            try:
                symlink_path.symlink_to(tmp_path)
            except (OSError, NotImplementedError) as e:
                raise unittest.SkipTest(f"Symlinks not supported or permitted on this environment: {e}")

            # Verify resolve_workspace_path detects the symlink escape
            with self.assertRaises(PermissionError):
                server.resolve_workspace_path(f"_boundary_test_dir/{symlink_path.name}")

            res = server.run_skill({}, "READ_FILE", f"_boundary_test_dir/{symlink_path.name}")
            self.assertEqual(res, "Path is outside the Nova workspace.")
        finally:
            if symlink_path.is_symlink() or symlink_path.exists():
                try:
                    symlink_path.unlink()
                except Exception:
                    pass
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def test_override_and_system_folder_protection(self):
        # Even with allow_outside_workspace=True, system folders are strictly rejected
        cfg_override = {"allow_outside_workspace": True}
        system_path = r"C:\Windows\System32\drivers\etc\hosts" if platform.system() == "Windows" else "/etc/passwd"
        
        with self.assertRaises(PermissionError):
            server.resolve_workspace_path(system_path, cfg=cfg_override)

        res = server.run_skill(cfg_override, "WRITE_FILE", f"{system_path} | blocked write")
        self.assertEqual(res, "Path is outside the Nova workspace.")

    def test_HIGH_02_nova_browser_refuses_outside_workspace_and_requires_confirm_for_local(self):
        """Regression test for HIGH-02:
        - nova_browser refuses file:// and local filesystem paths outside workspace
        - local paths go through resolve_workspace_path and sensitive-file check
        - BROWSER_RESEARCH/OPEN require confirmation for any local path
        - Tests traversal, symlink, case variants, and file:///C:/ forms
        """
        import nova_browser
        import ctypes

        # 1. Workspace file is allowed by normalize_target_url
        safe_html = self.test_sub_dir / "safe_doc.html"
        safe_html.write_text("<html><body>safe</body></html>", encoding="utf-8")
        uri = nova_browser.normalize_target_url("_boundary_test_dir/safe_doc.html")
        self.assertTrue(uri.startswith("file:///"))
        self.assertIn("safe_doc.html", uri)

        # 2. Traversal outside workspace rejected
        for trav in ("../server.py", "..\\data\\config.json", "../../outside.txt", "_boundary_test_dir/../../server.py"):
            with self.assertRaises(PermissionError, msg=f"Traversal {trav} should be blocked"):
                nova_browser.normalize_target_url(trav)
            res_ro = nova_browser.read_page_content(trav)
            self.assertIn("error", res_ro)

        # 3. file:///C:/ and file:// forms outside workspace rejected
        outside_win = "file:///C:/Windows/win.ini" if platform.system() == "Windows" else "file:///etc/passwd"
        outside_cfg = (server.ROOT / "data" / "config.json").resolve().as_uri()
        for f_uri in (outside_win, outside_cfg, "file:///C:/Windows/System32/drivers/etc/hosts"):
            with self.assertRaises(PermissionError, msg=f"URI {f_uri} should be blocked"):
                nova_browser.normalize_target_url(f_uri)
            res_open = server.run_skill({}, "BROWSER_OPEN", f_uri)
            self.assertIn("Refused:", res_open)
            res_url = server.run_skill({}, "OPEN_URL", f_uri)
            self.assertIn("Refused:", res_url)

        # 4. Case variants on Windows rejected for sensitive / outside paths
        for variant in ("DATA/CONFIG.JSON", "Data\\Memory.JSON", "SERVER.PY", "Web/Index.html"):
            with self.assertRaises(PermissionError, msg=f"Case variant {variant} should be blocked"):
                nova_browser.normalize_target_url(variant)

        # 5. Sensitive filename inside workspace rejected
        sens_in_ws = self.test_sub_dir / "config.json"
        sens_in_ws.write_text("{}", encoding="utf-8")
        with self.assertRaises(PermissionError):
            nova_browser.normalize_target_url("_boundary_test_dir/config.json")

        # 6. Symlink / junction inside workspace pointing outside rejected in nova_browser
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
            tmp.write(b"<html>secret</html>")
            ext_path = Path(tmp.name).resolve()
        sym_file = self.test_sub_dir / "sym_out.html"
        try:
            created_link = False
            try:
                sym_file.symlink_to(ext_path)
                created_link = True
            except (OSError, NotImplementedError):
                pass
            if created_link:
                with self.assertRaises(PermissionError):
                    nova_browser.normalize_target_url("_boundary_test_dir/sym_out.html")
                with self.assertRaises(PermissionError):
                    nova_browser.normalize_target_url(sym_file.as_uri())
        finally:
            try:
                sym_file.unlink(missing_ok=True)
            except Exception:
                pass
            try:
                ext_path.unlink(missing_ok=True)
            except Exception:
                pass

        # 7. BROWSER_RESEARCH and BROWSER_OPEN require confirmation for ANY local path
        cfg_default = {"confirm_destructive": True}
        for tool in ("BROWSER_RESEARCH", "BROWSER_OPEN", "OPEN_URL", "OPEN_FILE", "VIEW_FILE"):
            for local_arg in ("_boundary_test_dir/safe_doc.html", str(safe_html), safe_html.as_uri(), "file:///C:/Windows/win.ini"):
                req_conf, reason = server.check_tool_confirmation_required(cfg_default, tool, local_arg, is_tainted=False, source="pc")
                self.assertTrue(req_conf, f"{tool} with local path '{local_arg}' must require confirmation")
                self.assertIn("local path", reason.lower())

        # Web URL for BROWSER_RESEARCH still does not trigger the local-path confirmation rule
        req_web, _ = server.check_tool_confirmation_required(cfg_default, "BROWSER_RESEARCH", "https://example.com", is_tainted=False, source="pc")
        self.assertFalse(req_web)

    def test_HIGH_03_skill_organize_folder_never_continues_after_permission_error(self):
        """Regression test for HIGH-03:
        skill_organize_folder must never continue after PermissionError when allow_outside_workspace=False.
        """
        with tempfile.TemporaryDirectory() as ext_dir:
            ext_path = Path(ext_dir)
            sample_pdf = ext_path / "report.pdf"
            sample_pdf.write_text("external pdf content", encoding="utf-8")

            # With default config (allow_outside_workspace=False), organizing external folder is refused
            res = server.skill_organize_folder(str(ext_path), cfg={"allow_outside_workspace": False})
            self.assertIn("outside the Nova workspace", res)
            # File was NOT moved
            self.assertTrue(sample_pdf.exists())
            self.assertFalse((ext_path / "Documents" / "report.pdf").exists())

            # Traversal and 'downloads' alias are also blocked when allow_outside_workspace=False
            res_trav = server.skill_organize_folder("../..", cfg={"allow_outside_workspace": False})
            self.assertIn("outside the Nova workspace", res_trav)
            res_dl = server.skill_organize_folder("downloads", cfg={"allow_outside_workspace": False})
            self.assertIn("outside the Nova workspace", res_dl)

            # Sensitive Nova directory (e.g. ROOT or data/) is blocked even when allow_outside_workspace=True
            res_root = server.skill_organize_folder(str(server.ROOT), cfg={"allow_outside_workspace": True})
            self.assertIn("Access denied", res_root)

    def test_HIGH_04_is_sensitive_nova_file_comprehensive_protection(self):
        """Regression test for HIGH-04:
        is_sensitive_nova_file denies by default everything under data/, all project source files
        (*.py, web/, skills/, build files), .git, and backups; resolves symlinks/junctions,
        compares case-insensitively on Windows, and handles 8.3 short names.
        """
        import subprocess
        import ctypes

        cfg_allow_out = {"allow_outside_workspace": True}

        # 1. Everything under data/, source files, web/, skills/, build files, .git, backups
        must_be_sensitive = [
            server.ROOT / "data" / "config.json",
            server.ROOT / "data" / "secrets.json",
            server.ROOT / "data" / "memory.json",
            server.ROOT / "data" / "audit.jsonl",
            server.ROOT / "data" / "usage.jsonl",
            server.ROOT / "data" / "nova_brain.db",
            server.ROOT / "data" / "arbitrary_future_file.txt",
            server.ROOT / "server.py",
            server.ROOT / "nova_browser.py",
            server.ROOT / "guardian_agent.py",
            server.ROOT / "web" / "app.js",
            server.ROOT / "web" / "index.html",
            server.ROOT / "skills" / "developer" / "tdd.md",
            server.ROOT / "build_exe.bat",
            server.ROOT / "run.bat",
            server.ROOT / "NovaAI_Installer.iss",
            server.ROOT / ".git" / "config",
            server.ROOT / ".git" / "HEAD",
            self.test_sub_dir / "secret.bak",
            self.test_sub_dir / "db.corrupt",
            self.test_sub_dir / ".env.production",
        ]
        for p in must_be_sensitive:
            self.assertTrue(server.is_sensitive_nova_file(p), f"Expected {p} to be sensitive")
            with self.assertRaises(PermissionError, msg=f"resolve_workspace_path should block {p}"):
                server.resolve_workspace_path(str(p), cfg=cfg_allow_out)

        # 2. Normal user file inside workspace is NOT sensitive
        normal_ws_file = self.test_sub_dir / "notes.txt"
        normal_ws_file.write_text("hello", encoding="utf-8")
        self.assertFalse(server.is_sensitive_nova_file(normal_ws_file))

        # 3. Case variants on Windows
        if platform.system() == "Windows":
            case_variants = [
                server.ROOT / "DATA" / "MEMORY.JSON",
                server.ROOT / "Server.PY",
                server.ROOT / "WEB" / "APP.JS",
                server.ROOT / "SKILLS" / "DEVELOPER" / "TDD.MD",
                server.ROOT / ".GIT" / "CONFIG",
            ]
            for cv in case_variants:
                self.assertTrue(server.is_sensitive_nova_file(cv), f"Case variant {cv} must be detected as sensitive")
                with self.assertRaises(PermissionError):
                    server.resolve_workspace_path(str(cv), cfg=cfg_allow_out)

        # 4. Windows 8.3 short path handling
        if platform.system() == "Windows":
            long_dir = server.ROOT / "data"
            buf = ctypes.create_unicode_buffer(1024)
            res_short = ctypes.windll.kernel32.GetShortPathNameW(str(long_dir), buf, 1024)
            if res_short > 0 and buf.value:
                short_cfg = Path(buf.value) / "config.json"
                self.assertTrue(server.is_sensitive_nova_file(short_cfg))
                with self.assertRaises(PermissionError):
                    server.resolve_workspace_path(str(short_cfg), cfg=cfg_allow_out)

            # Also simulate an 8.3 path via _expand_windows_8dot3 mock to guarantee coverage even on volumes with 8dot3 disabled
            fake_short = Path(r"C:\PROGRA~1\NovaFake\data\config.json")
            real_target = str(server.ROOT / "data" / "config.json")
            orig_expand = server._expand_windows_8dot3
            def mocked_expand(p_str):
                if "PROGRA~1" in str(p_str):
                    return real_target
                return orig_expand(p_str)
            from unittest.mock import patch
            with patch("server._expand_windows_8dot3", side_effect=mocked_expand):
                self.assertTrue(server.is_sensitive_nova_file(fake_short))

        # 5. Junction / symlink inside workspace pointing to ROOT/data or ROOT/web
        junc_dir = self.test_sub_dir / "linked_data"
        try:
            linked = False
            if platform.system() == "Windows":
                proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(junc_dir), str(server.ROOT / "data")], capture_output=True, text=True)
                linked = (proc.returncode == 0)
            else:
                try:
                    junc_dir.symlink_to(server.ROOT / "data", target_is_directory=True)
                    linked = True
                except Exception:
                    pass
            if linked:
                junc_target = junc_dir / "memory.json"
                self.assertTrue(server.is_sensitive_nova_file(junc_target))
                with self.assertRaises(PermissionError):
                    server.resolve_workspace_path(str(junc_target), cfg=cfg_allow_out)
        finally:
            if junc_dir.exists() or junc_dir.is_symlink():
                if platform.system() == "Windows":
                    subprocess.run(["cmd", "/c", "rmdir", str(junc_dir)], capture_output=True)
                else:
                    junc_dir.unlink(missing_ok=True)

    def test_batch1b_1_all_browser_navigation_entry_points_refuse_outside_and_unc(self):
        """Batch 1b item 1:
        Enforce workspace/sensitive-file check inside nova_browser.open_new_tab and every function
        that navigates or opens a URL (open_or_activate, activate/navigate, BROWSER_YOUTUBE, launch_browser,
        read_page_content, open_url). Test with file:///C:/Windows/win.ini, C:\\Windows\\win.ini,
        \\\\server\\share\\x, and file://localhost/C:/Windows/win.ini - all must be refused.
        """
        import nova_browser

        forbidden_targets = [
            "file:///C:/Windows/win.ini",
            r"C:\Windows\win.ini",
            r"\\server\share\x",
            "file://localhost/C:/Windows/win.ini",
        ]
        for target in forbidden_targets:
            with self.assertRaises(PermissionError, msg=f"normalize_target_url must refuse {target}"):
                nova_browser.normalize_target_url(target)
            with self.assertRaises(PermissionError, msg=f"open_new_tab must refuse {target}"):
                nova_browser.open_new_tab(target)
            with self.assertRaises(PermissionError, msg=f"open_or_activate must refuse {target}"):
                nova_browser.open_or_activate(target)
            with self.assertRaises(PermissionError, msg=f"launch_browser must refuse {target}"):
                nova_browser.launch_browser(target)

            res_read = nova_browser.read_page_content(target)
            self.assertIn("error", res_read, f"read_page_content must refuse {target}")

            res_yt = nova_browser.youtube_action("play", target)
            self.assertIn("Refused:", res_yt, f"youtube_action must refuse {target}")

            res_skill_yt = server.run_skill({}, "BROWSER_YOUTUBE", f"play | {target}")
            self.assertIn("Refused:", res_skill_yt, f"BROWSER_YOUTUBE skill must refuse {target}")

            res_skill_act = server.run_skill({}, "BROWSER_ACTIVATE", target)
            self.assertIn("Refused:", res_skill_act, f"BROWSER_ACTIVATE skill must refuse {target}")

            res_skill_open = server.run_skill({}, "BROWSER_OPEN", target)
            self.assertIn("Refused:", res_skill_open, f"BROWSER_OPEN skill must refuse {target}")

            res_open_url = server.open_url(target)
            self.assertIn("Refused:", res_open_url, f"open_url must refuse {target}")

    def test_batch1b_2_is_local_target_no_false_positives_on_urls_or_shorthands(self):
        """Batch 1b item 2:
        Fix is_local_target: delete the 'slash without a dot in the first segment' heuristic.
        localhost:3000/dashboard, 127.0.0.1:8765/x, react/redux, github.com/user/repo must NOT be treated as local.
        """
        import nova_browser

        non_local_samples = [
            "localhost:3000/dashboard",
            "example.com:8080/x",
            "react/redux",
            "github.com/user/repo",
            "https://github.com/user/repo",
            "http://localhost:3000/dashboard",
        ]
        for sample in non_local_samples:
            self.assertFalse(nova_browser.is_local_target(sample), f"'{sample}' must NOT be treated as a local target")

        # Verify normalize_target_url treats them as web URLs or search queries without raising PermissionError
        self.assertEqual(nova_browser.normalize_target_url("example.com:8080/x"), "https://example.com:8080/x")
        self.assertEqual(nova_browser.normalize_target_url("github.com/user/repo"), "https://github.com/user/repo")
        self.assertTrue(nova_browser.normalize_target_url("react/redux").startswith("https://www.google.com/search?q="))

        # True local targets are still detected
        ws_file = self.test_sub_dir / "local_check.txt"
        ws_file.write_text("hi", encoding="utf-8")
        true_local_samples = [
            "file:///C:/Windows/win.ini",
            r"C:\Windows\win.ini",
            r"\\server\share\x",
            "/etc/passwd",
            "./notes.txt",
            "../server.py",
            "_boundary_test_dir/local_check.txt",
        ]
        for sample in true_local_samples:
            self.assertTrue(nova_browser.is_local_target(sample), f"'{sample}' MUST be treated as a local target")

    def test_batch1b_3_executable_extensions_and_tainted_markup_confirmations(self):
        """Batch 1b item 3:
        - Add to EXECUTABLE_EXTENSIONS: .hta .reg .scr .com .pif .jar .msi .dll .psm1 .url .chm
        - In a tainted turn, WRITE_FILE/EDIT_FILE of .html .htm .svg requires confirmation
        - BROWSER_OPEN of an HTML file written in a tainted turn requires confirmation
        """
        new_exec_exts = [".hta", ".reg", ".scr", ".com", ".pif", ".jar", ".msi", ".dll", ".psm1", ".url", ".chm"]
        for ext in new_exec_exts:
            self.assertIn(ext, server.EXECUTABLE_EXTENSIONS)
            # Even with confirm_destructive=False and is_tainted=False, executable extensions ALWAYS require confirmation
            req, reason = server.check_tool_confirmation_required(
                {"confirm_destructive": False}, "WRITE_FILE", f"payload{ext} | content", is_tainted=False, source="pc"
            )
            self.assertTrue(req, f"WRITE_FILE to {ext} must always require confirmation")
            self.assertIn(ext, reason)

        # In a tainted turn, WRITE_FILE / EDIT_FILE of .html, .htm, .svg requires confirmation (even if confirm_destructive=False)
        for m_ext in (".html", ".htm", ".svg"):
            for tool in ("WRITE_FILE", "EDIT_FILE"):
                req_t, reason_t = server.check_tool_confirmation_required(
                    {"confirm_destructive": False}, tool, f"page{m_ext} | <svg></svg>", is_tainted=True, source="pc"
                )
                self.assertTrue(req_t, f"Tainted {tool} to {m_ext} must require confirmation")
                self.assertIn(m_ext, reason_t)

        # BROWSER_OPEN of an HTML file written in a tainted turn requires confirmation (even if confirm_destructive=False)
        server.record_workspace_write("tainted_report.html", is_tainted=True)
        req_open, reason_open = server.check_tool_confirmation_required(
            {"confirm_destructive": False}, "BROWSER_OPEN", "tainted_report.html", is_tainted=False, source="pc"
        )
        self.assertTrue(req_open)
        self.assertIn("tainted turn", reason_open.lower())

    def test_batch1b_4_system_folders_refused_with_allow_outside_workspace_and_downloads_message(self):
        """Batch 1b item 4:
        - Verify resolve_workspace_path still enforces is_system_folder when allow_outside_workspace=True.
        - Organizing C:\\Windows and C:\\Program Files is refused even with allow_outside_workspace=True.
        - Improve the 'Downloads' refusal message to explain the setting.
        """
        cfg_outside = {"allow_outside_workspace": True}
        if platform.system() == "Windows":
            sys_targets = [r"C:\Windows", r"C:\Program Files", r"C:\Windows\System32"]
        else:
            sys_targets = ["/etc", "/usr", "/bin"]

        for st in sys_targets:
            with self.assertRaises(PermissionError, msg=f"resolve_workspace_path must block system folder {st}"):
                server.resolve_workspace_path(st, cfg=cfg_outside)
            res_org = server.skill_organize_folder(st, cfg=cfg_outside)
            self.assertTrue(
                "Access denied" in res_org or "outside the Nova workspace" in res_org,
                f"Expected refusal organizing system folder {st}, got: {res_org}"
            )

        # Downloads refusal message explains allow_outside_workspace setting when allow_outside_workspace=False
        res_dl = server.skill_organize_folder("Downloads", cfg={"allow_outside_workspace": False})
        self.assertIn("allow_outside_workspace", res_dl)
        self.assertIn("Downloads", res_dl)

    def test_batch1b_5_sensitive_location_denylist_even_with_allow_outside_workspace(self):
        """Batch 1b item 5:
        Sensitive-location deny list that applies even when allow_outside_workspace=True:
        ~/.ssh, ~/.aws, ~/.config, ~/.gnupg, %APPDATA%, %LOCALAPPDATA% (browser profiles, Credentials),
        Windows\\System32\\config, any .env/.pem/.key/id_rsa/*.kdbx/wallet.dat file.
        """
        cfg_outside = {"allow_outside_workspace": True}
        home = Path.home()
        sensitive_paths = [
            home / ".ssh" / "authorized_keys",
            home / ".aws" / "credentials",
            home / ".config" / "gcloud" / "credentials.db",
            home / ".gnupg" / "secring.gpg",
            Path(r"C:\Windows\System32\config\SAM") if platform.system() == "Windows" else Path("/etc/shadow"),
            self.test_sub_dir / ".env",
            self.test_sub_dir / ".env.local",
            self.test_sub_dir / "server.pem",
            self.test_sub_dir / "private.key",
            self.test_sub_dir / "id_rsa",
            self.test_sub_dir / "passwords.kdbx",
            self.test_sub_dir / "wallet.dat",
        ]
        if platform.system() == "Windows":
            appdata = os.environ.get("APPDATA") or str(home / "AppData" / "Roaming")
            localappdata = os.environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
            sensitive_paths.extend([
                Path(appdata) / "Microsoft" / "Credentials",
                Path(localappdata) / "Google" / "Chrome" / "User Data" / "Default" / "Login Data",
                Path(localappdata) / "Microsoft" / "Edge" / "User Data" / "Default" / "Cookies",
            ])

        for sp in sensitive_paths:
            self.assertTrue(
                server.is_sensitive_nova_file(sp),
                f"Expected {sp} to be blocked by sensitive location denylist"
            )
            with self.assertRaises(PermissionError, msg=f"resolve_workspace_path must block {sp} even with allow_outside_workspace=True"):
                server.resolve_workspace_path(str(sp), cfg=cfg_outside)


if __name__ == "__main__":
    unittest.main()
