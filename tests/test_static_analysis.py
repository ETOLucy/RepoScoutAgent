import unittest

from src.reposcout.static_analysis import manifest_signals


class StaticAnalysisTest(unittest.TestCase):
    def test_extracts_dependencies_from_supported_manifests(self):
        cases = [
            (
                "package.json",
                '{"dependencies":{"passport-saml":"1"},"devDependencies":{"vitest":"2"}}',
                ["passport-saml", "vitest"],
            ),
            (
                "pyproject.toml",
                '[project]\ndependencies=["fastapi>=1", "authlib"]',
                ["fastapi>=1", "authlib"],
            ),
            ("Cargo.toml", '[dependencies]\naxum="1"\nserde={version="1"}', ["axum", "serde"]),
            ("go.mod", "require github.com/coreos/go-oidc v3.0.0", ["github.com/coreos/go-oidc"]),
            ("requirements.txt", "Authlib==1.3\n# ignored\n-r base.txt", ["authlib"]),
        ]

        for path, content, expected in cases:
            with self.subTest(path=path):
                self.assertEqual(manifest_signals(path, content), expected)

    def test_malformed_manifest_returns_no_generated_evidence(self):
        self.assertEqual(manifest_signals("package.json", "not-json"), [])


if __name__ == "__main__":
    unittest.main()
