# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html), and a released section
is generated from the issues that release closed. Notes that predate an issue sit
under `Unreleased`, and are the only part of this file written by hand.

## [Unreleased]

## [v0.2.2] - 2026-11-18

### Security

- control: an anonymous ListBuckets is refused at the gateway ([#119](https://github.com/mathewmusango/emuplane/issues/119))

## [v0.2.1] - 2026-11-18

### Fixed

- compose: the all-in-one stack runs the pinned emulator, and the README says so ([#106](https://github.com/mathewmusango/emuplane/issues/106))

### Security

- control: the access point parser refuses a document that declares entities ([#99](https://github.com/mathewmusango/emuplane/issues/99))
- control: every XML parser refuses a DTD, and defusedxml is pinned ([#102](https://github.com/mathewmusango/emuplane/issues/102))
- control: response headers cannot carry a line break, and an email is bounded before its pattern ([#116](https://github.com/mathewmusango/emuplane/issues/116))

## [v0.2.0] - 2026-11-18

### Added

- S3 console: upload objects and edit them in place ([#89](https://github.com/mathewmusango/emuplane/issues/89))
- S3 console: versions, incomplete uploads and object ACLs ([#90](https://github.com/mathewmusango/emuplane/issues/90))
- S3 console: bucket properties, permissions and configuration ([#91](https://github.com/mathewmusango/emuplane/issues/91))
- S3: enforce MFA delete at the gateway ([#92](https://github.com/mathewmusango/emuplane/issues/92))
- S3 console: access points, Multi-Region and Object Lambda ([#93](https://github.com/mathewmusango/emuplane/issues/93))

### Changed

- S3 console: browse buckets and objects as folders ([#88](https://github.com/mathewmusango/emuplane/issues/88))

### Fixed

- S3: page every listing instead of truncating it ([#94](https://github.com/mathewmusango/emuplane/issues/94))

## [v0.1.2] - 2026-11-17

### Fixed

- The release publishes without its SBOM, checksums and digest ([#62](https://github.com/mathewmusango/emuplane/issues/62))
- The release plan re-opens a release that already shipped ([#63](https://github.com/mathewmusango/emuplane/issues/63))

## [v0.1.1] - 2026-11-17

### Fixed

- The release image scans its own pip, and fails ([#57](https://github.com/mathewmusango/emuplane/issues/57))

## [v0.1.0] - 2026-11-17

### Added

- Accounts are created the way AWS creates them: root owns the account, IAM users join it, and one address signs in one principal. ([#1](https://github.com/mathewmusango/emuplane/issues/1))
- The gateway maps each request to its account and its enabled regions, then forwards it untouched. ([#2](https://github.com/mathewmusango/emuplane/issues/2))
- Buckets and objects are listed, opened, uploaded, copied, tagged and deleted from the console. ([#3](https://github.com/mathewmusango/emuplane/issues/3))
- Access points open in full, including the Multi-Region create operation described by its token. ([#4](https://github.com/mathewmusango/emuplane/issues/4))
- Every advertised S3 operation is tested, and the coverage ledger is generated rather than claimed. ([#5](https://github.com/mathewmusango/emuplane/issues/5))
- Emulators are profiles, selected in .env rather than forked. ([#6](https://github.com/mathewmusango/emuplane/issues/6))
- The documentation site publishes from the repository and keeps a copy per release. ([#9](https://github.com/mathewmusango/emuplane/issues/9))
- The changelog is generated from issues, and CI refuses a change with no issue behind it. ([#10](https://github.com/mathewmusango/emuplane/issues/10))
- A deployment is an env file and a compose file; nothing else needs running. ([#15](https://github.com/mathewmusango/emuplane/issues/15))
- A release's tag, changelog, docs version and image are checked as one set. ([#17](https://github.com/mathewmusango/emuplane/issues/17))
- Every release publishes the image's SBOM, its checksum and the digest to pin. ([#18](https://github.com/mathewmusango/emuplane/issues/18))
- The documentation says where the console and the gateway answer. ([#24](https://github.com/mathewmusango/emuplane/issues/24))
- Bucket configuration is complete in the console, with every operation tested. ([#25](https://github.com/mathewmusango/emuplane/issues/25))
- Object tags, annotations, retention and legal hold are managed from the console. ([#26](https://github.com/mathewmusango/emuplane/issues/26))
- Multipart uploads can be started, completed and aborted. ([#27](https://github.com/mathewmusango/emuplane/issues/27))
- Multi-Region access points are created, described, dialled and deleted from the console. ([#28](https://github.com/mathewmusango/emuplane/issues/28))
- Object Lambda access points read back in full, not just as a row. ([#29](https://github.com/mathewmusango/emuplane/issues/29))
- Access points are created, read, given a policy and deleted. ([#30](https://github.com/mathewmusango/emuplane/issues/30))

### Fixed

- A root with no email address signs in by its account name. ([#12](https://github.com/mathewmusango/emuplane/issues/12))
- The sign-in landing page offers the password reset route. ([#13](https://github.com/mathewmusango/emuplane/issues/13))
- The deployment overlay no longer shadows the published compose file. ([#14](https://github.com/mathewmusango/emuplane/issues/14))
- The start script pulls the published image instead of assuming a build. ([#16](https://github.com/mathewmusango/emuplane/issues/16))
- The documentation's screenshot matches the console, and its images are checked. ([#21](https://github.com/mathewmusango/emuplane/issues/21))
- One brand file feeds the console's icons and the documentation's mark. ([#22](https://github.com/mathewmusango/emuplane/issues/22))
- The example addresses the deployment with no reverse proxy. ([#23](https://github.com/mathewmusango/emuplane/issues/23))
- The release plan reads pull requests instead of issues ([#55](https://github.com/mathewmusango/emuplane/issues/55))

### Security

- The container runs unprivileged, read-only, with no capabilities. ([#7](https://github.com/mathewmusango/emuplane/issues/7))
- Every read and write is scoped to the caller's account, and the bearer token is the only way across. ([#8](https://github.com/mathewmusango/emuplane/issues/8))
- An email address belongs to one principal, so a password reset can no longer land on another account. ([#11](https://github.com/mathewmusango/emuplane/issues/11))
- `main` accepts pull requests only, and nobody bypasses it. ([#19](https://github.com/mathewmusango/emuplane/issues/19))
- Tags are immutable and branch names cannot collide with a release. ([#20](https://github.com/mathewmusango/emuplane/issues/20))
- The docs toolchain's audit fails on high and critical ([#52](https://github.com/mathewmusango/emuplane/issues/52))
