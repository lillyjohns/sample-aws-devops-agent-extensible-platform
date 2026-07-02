# Contributing Guidelines

Thank you for your interest in contributing to this project. Whether it's a bug report, new feature, correction, or additional documentation, we greatly value feedback and contributions from our community.

Please read through this document before submitting any issues or pull requests.

## Reporting Bugs/Feature Requests

We welcome you to use the GitHub issue tracker to report bugs or suggest features.

When filing an issue, please check existing open, or recently closed, issues to make sure somebody else hasn't already reported the issue. Please try to include as much information as you can:

- A reproducible test case or series of steps
- The version of the code being used
- Any modifications you've made relevant to the bug
- Anything unusual about your environment or deployment

## Contributing a new MCP target (capability pack)

The fastest way to contribute is a new Gateway capability:

1. Create a folder under `mcp-targets/<your-target>/`
2. Add a `manifest.yaml` following the schema in [docs/DESIGN.md](docs/DESIGN.md)
3. Keep it **read-only** (`readOnly: true` is enforced at synth time)
4. Declare least-privilege IAM permissions in the manifest
5. Include a short README in the folder explaining the tools it exposes and its **retirement condition** (when native DevOps Agent capability would make it obsolete)
6. Ship it with `enabled: false` unless it belongs in the default deployment

## Contributing via Pull Requests

1. You are working against the latest source on the `main` branch
2. You check existing open and recently merged pull requests
3. You open an issue to discuss any significant work first

To send us a pull request:

1. Fork the repository
2. Modify the source; please focus on the specific change you are contributing
3. Ensure local tests pass (`npm test` in `platform/`)
4. Commit to your fork using clear commit messages
5. Send us a pull request, answering any default questions in the pull request interface

## Security issue notifications

If you discover a potential security issue in this project we ask that you notify AWS/Amazon Security via our [vulnerability reporting page](http://aws.amazon.com/security/vulnerability-reporting/). Please do **not** create a public GitHub issue.

## Licensing

See the [LICENSE](LICENSE) file for our project's licensing. We will ask you to confirm the licensing of your contribution.
