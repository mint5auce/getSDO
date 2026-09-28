"""Exercise the CLI against a real local HTTP server, without NASA access."""

import datetime as dt
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import getSDO

ROOT = Path(__file__).resolve().parents[1]
JPEG = (ROOT / "tests" / "fixtures" / "pixel.jpg").read_bytes()
RUNNER = (
    "import getSDO, sys; getSDO.SDO_ROOT = sys.argv[1]; "
    "raise SystemExit(getSDO.main(sys.argv[2:]))"
)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.output = self.work / "folder with spaces" / "images"
        self.timestamp = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
        self.responses = {}
        self.delays = {}
        self.requests = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                owner.requests.append(self.path)
                status, headers, body = owner.responses.get(
                    self.path, (404, {}, b"not found")
                )
                time.sleep(owner.delays.get(self.path, 0))
                try:
                    self.send_response(status)
                    for name, value in headers.items():
                        self.send_header(name, value)
                    if "Content-Length" not in headers:
                        self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # Expected when testing the client's network timeout.

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.05},
            daemon=True,
        )
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        for channel in getSDO.VIEWS.values():
            self.add_observation(channel)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def add_observation(self, channel, timestamp=None, resolution=512):
        timestamp = timestamp or self.timestamp
        self.responses[f"/assets/img/latest/times{channel}.txt"] = (
            200,
            {"Content-Type": "text/plain"},
            f"{channel}: {timestamp:%Y%m%d_%H%M%S}\n".encode(),
        )
        image_path = (
            f"/assets/img/browse/{timestamp:%Y/%m/%d}/"
            f"{timestamp:%Y%m%d_%H%M%S}_{resolution}_{channel}.jpg"
        )
        self.responses[image_path] = (200, {"Content-Type": "image/jpeg"}, JPEG)
        return image_path

    def filename(self, view="aia_171", timestamp=None, resolution=512):
        timestamp = timestamp or self.timestamp
        return f"{view}_{timestamp:%Y%m%d_%H%M%S}_{resolution}_{getSDO.VIEWS[view]}.jpg"

    def cli(self, *args, default_output=False):
        options = [] if default_output else ["--output", str(self.output)]
        return subprocess.run(
            [sys.executable, "-c", RUNNER, self.base_url, *options, *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env={**os.environ, "HOME": str(self.work / "home")},
        )

    def one_view(self, *args):
        return self.cli("--views", "aia_171", "--resolution", "512", *args)

    def test_default_views_resolution_and_portable_destination(self):
        for channel in getSDO.VIEWS.values():
            self.add_observation(channel, resolution=4096)
        result = self.cli(default_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = self.work / "home" / "Pictures" / "sdo-feed"
        self.assertEqual(len(list(output.glob("*.jpg"))), 7)
        self.assertEqual(len(self.requests), 14)
        for view in getSDO.VIEWS:
            self.assertEqual(
                (output / self.filename(view, resolution=4096)).read_bytes(), JPEG
            )

    def test_repeat_run_skips_image_request_and_preserves_other_files(self):
        self.output.mkdir(parents=True)
        unrelated = self.output / "family-photo.jpg"
        unrelated.write_bytes(b"keep me")
        ds_store = self.output / ".DS_Store"
        ds_store.write_bytes(b"finder metadata")
        first = self.one_view()
        self.assertEqual(first.returncode, 0, first.stderr)
        target = self.output / self.filename()
        original_mtime = target.stat().st_mtime_ns
        self.requests.clear()
        second = self.one_view()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("Skipped:", second.stdout)
        self.assertEqual(self.requests, ["/assets/img/latest/times0171.txt"])
        self.assertEqual(target.stat().st_mtime_ns, original_mtime)
        self.assertEqual(unrelated.read_bytes(), b"keep me")
        self.assertEqual(ds_store.read_bytes(), b"finder metadata")

    def test_one_image_per_observation_day_and_force_override(self):
        first = self.one_view()
        self.assertEqual(first.returncode, 0, first.stderr)
        newer = self.timestamp.replace(second=(self.timestamp.second + 1) % 60)
        image_path = self.add_observation("0171", newer)
        self.requests.clear()
        skipped = self.one_view()
        self.assertEqual(skipped.returncode, 0, skipped.stderr)
        self.assertIn("Skipped:", skipped.stdout)
        self.assertNotIn(image_path, self.requests)
        forced = self.one_view("--force")
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertIn("Downloaded:", forced.stdout)
        self.assertEqual(len(list(self.output.glob("*.jpg"))), 2)

    def test_new_observation_day_downloads_another_image(self):
        first = self.one_view()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.add_observation("0171", self.timestamp + dt.timedelta(days=1))
        second = self.one_view()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("Downloaded:", second.stdout)
        self.assertEqual(len(list(self.output.glob("*.jpg"))), 2)

    def test_resolution_is_part_of_skip_decision(self):
        first = self.one_view()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.add_observation("0171", resolution=1024)
        second = self.cli("--views", "aia_171", "--resolution", "1024")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("Downloaded:", second.stdout)
        self.assertEqual(len(list(self.output.glob("*.jpg"))), 2)

    def test_existing_original_filename_from_earlier_time_is_recognised(self):
        self.output.mkdir(parents=True)
        earlier = self.timestamp.replace(second=(self.timestamp.second + 1) % 60)
        (self.output / self.filename(timestamp=earlier)).write_bytes(JPEG)
        result = self.one_view()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Skipped:", result.stdout)
        self.assertEqual(self.requests, ["/assets/img/latest/times0171.txt"])

    def test_empty_or_truncated_existing_file_is_repaired(self):
        self.output.mkdir(parents=True)
        target = self.output / self.filename()
        for data in (b"", JPEG[:-2]):
            with self.subTest(data=data[:8]):
                target.write_bytes(data)
                result = self.one_view()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Downloaded:", result.stdout)
                self.assertEqual(target.read_bytes(), JPEG)

    def test_stale_source_is_warned_about_on_download_and_skip(self):
        stale = self.timestamp - dt.timedelta(days=7)
        self.add_observation("0171", stale)
        for _ in range(2):
            result = self.one_view()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Warning: aia_171:", result.stderr)
            self.assertIn(f"{stale:%Y-%m-%d}", result.stderr)
        self.assertTrue((self.output / self.filename(timestamp=stale)).is_file())

    def test_invalid_timestamp_is_reported_without_traceback(self):
        for body in (
            b"",
            b"<html>maintenance</html>",
            b"0193: 20260921_153805",
            b"0171: 20261321_152646",
            b"0171: ../../bad",
            b"\xff",
        ):
            with self.subTest(body=body):
                self.responses["/assets/img/latest/times0171.txt"] = (200, {}, body)
                result = self.one_view()
                self.assertEqual(result.returncode, 1)
                self.assertIn("Error: aia_171:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(list(self.output.iterdir()))

    def test_failed_view_does_not_prevent_other_downloads(self):
        self.responses["/assets/img/latest/times0131.txt"] = (503, {}, b"unavailable")
        result = self.cli("--views", "aia_131", "aia_171", "--resolution", "512")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Error: aia_131:", result.stderr)
        self.assertIn("HTTP Error 503", result.stderr)
        self.assertEqual((self.output / self.filename()).read_bytes(), JPEG)

    def test_bad_download_preserves_existing_image(self):
        initial = self.one_view()
        self.assertEqual(initial.returncode, 0, initial.stderr)
        path = self.add_observation("0171")
        bad_responses = (
            (404, {}, b"not found"),
            (200, {"Content-Type": "text/html"}, b"<html>error</html>"),
            (200, {"Content-Type": "image/jpeg"}, b"not a JPEG"),
            (200, {"Content-Type": "image/jpeg"}, JPEG[:-2]),
            (
                200,
                {"Content-Type": "image/jpeg", "Content-Length": str(len(JPEG) + 10)},
                JPEG,
            ),
        )
        for response in bad_responses:
            with self.subTest(response=response[:2]):
                self.responses[path] = response
                result = self.one_view("--force")
                self.assertEqual(result.returncode, 1)
                self.assertIn("Error: aia_171:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual((self.output / self.filename()).read_bytes(), JPEG)
                self.assertFalse(list(self.output.glob(".getSDO-*")))

    def test_write_failure_cleans_temporary_file_and_preserves_existing_image(self):
        self.output.mkdir(parents=True)
        target = self.output / "existing.jpg"
        target.write_bytes(b"original contents")
        image_path = self.add_observation("0171")
        with (
            patch.object(Path, "replace", side_effect=OSError("disk write failed")),
            self.assertRaisesRegex(OSError, "disk write failed"),
        ):
            getSDO.save_image(self.base_url + image_path, target, 2)
        self.assertEqual(target.read_bytes(), b"original contents")
        self.assertEqual(list(self.output.iterdir()), [target])

    def test_oversized_image_is_rejected(self):
        image_path = self.add_observation("0171")
        target = self.work / "oversized.jpg"
        with (
            patch.object(getSDO, "MAX_IMAGE_BYTES", len(JPEG) - 1),
            self.assertRaisesRegex(ValueError, "exceeds"),
        ):
            getSDO.save_image(self.base_url + image_path, target, 2)
        self.assertFalse(target.exists())

    def test_network_timeout_is_reported(self):
        self.delays["/assets/img/latest/times0171.txt"] = 0.2
        result = self.one_view("--timeout", "0.02")
        self.assertEqual(result.returncode, 1)
        self.assertIn("timed out", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_output_path_that_is_a_file_fails_before_network_access(self):
        self.output.parent.mkdir(parents=True)
        self.output.write_text("keep me")
        result = self.one_view()
        self.assertEqual(result.returncode, 1)
        self.assertIn("Error creating output folder", result.stderr)
        self.assertEqual(self.output.read_text(), "keep me")
        self.assertFalse(self.requests)

    def test_repeated_views_are_requested_only_once(self):
        result = self.cli("--views", "aia_171", "aia_171", "--resolution", "512")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.requests), 2)

    def test_bad_arguments_fail_before_network_access(self):
        for args in (
            ["--views", "unknown"],
            ["--resolution", "999"],
            ["--timeout", "0"],
            ["--timeout", "-1"],
            ["--timeout", "nan"],
            ["--timeout", "inf"],
            ["--timeout", "abc"],
        ):
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(self.requests)

    def test_script_entry_point_help_does_not_download(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "getSDO.py"), "--help"],
            cwd=self.work,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--output", result.stdout)
        self.assertIn("--force", result.stdout)
        self.assertFalse(self.requests)


if __name__ == "__main__":
    unittest.main()
