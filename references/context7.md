# Context7 Retrieval Guide

Use Context7 for semantic retrieval over a finalist's repository code and official documentation.
It complements live GitHub discovery; it does not replace candidate discovery or guarantee coverage
of every GitHub repository.

## Tool sequence

1. Call the Context7 library-resolution tool with the exact `owner/repository`, canonical project
   name, and the confirmed user goal.
2. Select the result whose source repository and project identity match. Do not select solely by a
   similar display name.
3. Call the Context7 documentation-query tool with focused, answerable questions.
4. Preserve useful source URLs returned by Context7 for the final response.

Tool names may be exposed as `resolve-library-id` and `query-docs`, with an MCP namespace added by
the host. Use the Context7 tools provided by the dependency rather than guessing HTTP endpoints.

## Query plan

Ask only questions needed for the decision. Useful patterns include:

- `What is this project's primary product purpose and intended user?`
- `How does the official installation documentation deploy it with Docker?`
- `Where is capability X documented or implemented?`
- `What components, services, databases, or queues are required in production?`
- `What official integration point supports protocol/API X?`
- `What limitations, migration requirements, or breaking changes affect this use case?`

For composed solutions, query the shared interface from both sides. For example, retrieve the
producer's S3 support and the consumer's S3 configuration separately before calling them compatible.

## Coverage fallback

When resolution fails:

1. Retry once with the canonical name and exact GitHub URL.
2. Use available GitHub repository or browser tools to read README, official docs, releases, and the
   smallest relevant source slices.
3. State the conclusion normally, but do not label it as Context7-derived.

When Context7 itself is unavailable, continue with live GitHub and official sources. Mention the
degradation only when it materially limits the recommendation.

## Retrieval discipline

- Do not dump entire Context7 responses into the answer.
- Do not ask one giant question covering all candidates and criteria.
- Do not infer runtime behavior from a dependency name alone.
- Prefer current official documentation for setup and compatibility claims.
- Use code context for architecture or implementation questions, not as a substitute for product
  judgment.

