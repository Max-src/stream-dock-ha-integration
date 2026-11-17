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
- GitHub Actions: **Validate** (hassfest, and the Marketplace's own check) every day and on each push, and **Tests** (pytest and the card's tests). The Marketplace check is skipped while the repository is private, because it can only read public repositories.
- Install steps for the Marketplace, HACS and by hand, My Home Assistant buttons for the repository, the setup and each blueprint, and issue forms.
- README parts only meant for GitHub (Development) are kept out of the Marketplace's copy between `ha-marketplace:exclude` comments.

## Going public

The Marketplace and HACS only work with public repositories: until then, only the copy by hand works, and the buttons in the README lead nowhere for anyone else.

1. Make both repositories public: **Settings > General > Danger Zone > Change visibility**. The app's first, as the integration's install steps start there.
2. Check the repository's **About** (description and topics) and that **Issues** are on. The catalog's review checks all three.
3. Open **Actions**, run **Validate** and wait until both jobs pass, the Marketplace check included, now that it runs.
4. Run `publish-release.ps1`, so there's a full release made after the checks passed.
5. Try it as a user would: in Home Assistant, **Settings > Marketplace > Add from link**, enter `Max-src/stream-dock-ha-integration`, download it and restart. A copy made by hand should be deleted first (see the release notes).

## Getting listed in the Marketplace

The catalog is still the `hacs/default` repository, and only the owner of a repository can ask for it to be added:

1. Fork [hacs/default](https://github.com/hacs/default) to your own account (not an organisation), and make a branch from `master`.
2. In the file named `integration`, add `"Max-src/stream-dock-ha-integration"` in alphabetical order, not at the end.
3. Open a pull request and fill in its template completely: links to the latest release, to a passing **Validate** run's Marketplace check (with nothing ignored) and to a passing hassfest run. An incomplete template gets the pull request closed.
4. Its own checks then run: brands, the manifest, a clash with a Home Assistant domain, releases, owner, licence, description, topics and issues. Reviews take months, and asking people to review doesn't help.

The manifest's `"categories"` (`buttons_remotes`, `computers_network`) come from [Home Assistant's list](https://contributors.home-assistant.io/core/integrations/categories/). The Marketplace check fails on a name that isn't in it.
