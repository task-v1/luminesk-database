# Changelog

This file records catalog-policy and tooling changes. Individual recipe changes
remain versioned by `[package].version` in each `database/<name>/luminesk.toml`.

## Unreleased

- Reject generic, encrypted, RSA, DSA, EC, OpenSSH, and PGP private-key material.
- Exercise compressed GitHub recipe responses in the CLI compatibility suite.
- Skip catalog validation and publication when `database/` is unchanged.
- Isolate catalog generation from the write-enabled publication job.
- Pin the tested Luminesk CLI and every external GitHub Action by commit SHA.
- Raise tooling branch coverage from 53% to 85% minimum.
