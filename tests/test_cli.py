import unittest

from main import ServerConfig, create_parser, parse_config


class CliTest(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(parse_config([]), ServerConfig())

    def test_runtime_options(self):
        config = parse_config(
            [
                "--host",
                "0.0.0.0",
                "--port",
                "9000",
                "--github-max-concurrency",
                "6",
                "--github-max-attempts",
                "5",
                "--web-search-max-queries",
                "3",
                "--web-search-results",
                "10",
                "--web-search-timeout",
                "2.5",
                "--requirement-timeout",
                "12",
            ]
        )

        self.assertEqual(config.host, "0.0.0.0")
        self.assertEqual(config.port, 9000)
        self.assertEqual(config.github_max_concurrency, 6)
        self.assertEqual(config.github_max_attempts, 5)
        self.assertEqual(config.web_search_max_queries, 3)
        self.assertEqual(config.web_search_results, 10)
        self.assertEqual(config.web_search_timeout, 2.5)
        self.assertEqual(config.requirement_timeout, 12)

    def test_help_lists_runtime_options(self):
        help_text = create_parser().format_help()

        self.assertIn("--port", help_text)
        self.assertIn("--github-max-concurrency", help_text)
        self.assertIn("--web-search-timeout", help_text)
        self.assertIn("--requirement-timeout", help_text)

    def test_rejects_invalid_values(self):
        with self.assertRaises(SystemExit):
            parse_config(["--port", "70000"])
        with self.assertRaises(SystemExit):
            parse_config(["--github-max-concurrency", "0"])


if __name__ == "__main__":
    unittest.main()
