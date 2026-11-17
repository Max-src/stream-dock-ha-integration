# Publishing

How a new version gets out, and the steps left before the integration is listed in Home Assistant's Marketplace (HACS's catalog, built into Home Assistant since 2026.11).

The integration and the [app](https://github.com/Max-src/stream-dock-ha) are published side by side, and each one's README sends people to the other. Keep these in step:

- **Versions:** the table in the README's [Install](../README.md#install) section and the app's README say which app works with which integration. The app tells people which one to update when they don't match.
- **The protocol:** [`protocol.md`](protocol.md) here and the app's `docs/integration-protocol.md` are the same file.
- **Issues:** each repository's issue form points to the other one for problems on that side.

## A new version

1. Bump the version in `custom_components/stream_dock_ha/manifest.json`, `CARD_VERSION` in `frontend/stream-dock-card.js` and the test in `tests/test_connect.py`, all three the same.
2. Write what changed in [`release-notes.md`](release-notes.md).
3. Commit, then run `powershell -ExecutionPolicy Bypass -File .\publish-release.ps1`. It checks the versions agree, pushes, and makes a GitHub release `v<version>`. The Marketplace installs the latest release, not the latest commit, and "a tag alone is not enough".

## Already in place

- `hacs.json` with the name and the oldest Home Assistant it runs on.
- A manifest with everything the Marketplace and Home Assistant's own check (hassfest) look for: domain, name, version, documentation, issue tracker, code owner, keys in the expected order.
- The brand pictures in `custom_components/stream_dock_ha/brand/`, which Home Assistant 2026.3 and later use, so no request to the `home-assistant/brands` repository is needed.
- An MIT licence GitHub recognises.
- GitHub Actions: **Validate** (hassfest, and the Marketplace's own check) every day and on each push, and **Tests** (pytest and the card's tests).
- Install steps for the Marketplace, HACS and by hand, My Home Assistant buttons for the repository, the setup and each blueprint, and issue forms.
- README parts only meant for GitHub (Development) are kept out of the Marketplace's copy between `ha-marketplace:exclude` comments.

## The Marketplace listing

Both repositories are public. The listing was requested on 2026-11-17 in [hacs/default#14344](https://github.com/hacs/default/pull/14344), for release v0.1.13, with links to its passing Marketplace check and hassfest run. Reviews take months: never ask people to review it, which gets a pull request closed.

Until it's merged, people can add the repository by link (**Settings > Marketplace > Add from link**, `Max-src/stream-dock-ha-integration`). Once it's listed, each new release reaches users through the Marketplace, so keep releasing only after **Validate** passes.

The manifest's `"categories"` (`buttons_remotes`, `computers_network`) come from [Home Assistant's list](https://contributors.home-assistant.io/core/integrations/categories/). The Marketplace check fails on a name that isn't in it.
