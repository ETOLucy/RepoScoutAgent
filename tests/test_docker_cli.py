import os
import unittest
from unittest.mock import patch

from src.reposcout.docker_cli import create_parser, main


class DockerCliTest(unittest.TestCase):
    def test_help_describes_optional_proxy(self):
        help_text = create_parser().format_help()

        self.assertIn("--proxy", help_text)
        self.assertIn("use only when direct access fails", help_text)
        self.assertIn("--build", help_text)

    @patch("src.reposcout.docker_cli.subprocess.run")
    def test_up_passes_temporary_proxy_to_docker(self, run):
        run.return_value.returncode = 0

        result = main(["up", "--build", "--proxy", "http://127.0.0.1:7897"])

        self.assertEqual(result, 0)
        command = run.call_args.args[0]
        environment = run.call_args.kwargs["env"]
        self.assertEqual(command, ["docker", "compose", "up", "--build", "-d"])
        self.assertEqual(environment["HTTP_PROXY"], "http://127.0.0.1:7897")
        self.assertEqual(environment["HTTPS_PROXY"], "http://127.0.0.1:7897")
        self.assertIn("localhost", environment["NO_PROXY"])
        self.assertIn("127.0.0.1", environment["NO_PROXY"])

    @patch("src.reposcout.docker_cli.subprocess.run")
    def test_status_does_not_invent_proxy(self, run):
        run.return_value.returncode = 0
        clean_environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() not in {"HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"}
        }

        with patch.dict(os.environ, clean_environment, clear=True):
            result = main(["status"])

        self.assertEqual(result, 0)
        self.assertEqual(run.call_args.args[0], ["docker", "compose", "ps"])
        environment = run.call_args.kwargs["env"]
        self.assertNotIn("HTTP_PROXY", environment)
        self.assertNotIn("HTTPS_PROXY", environment)

    def test_rejects_invalid_proxy_and_action_flags(self):
        with self.assertRaises(SystemExit):
            main(["up", "--proxy", "127.0.0.1:7897"])
        with self.assertRaises(SystemExit):
            main(["status", "--build"])


if __name__ == "__main__":
    unittest.main()
