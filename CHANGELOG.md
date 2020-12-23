# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [2020.12.0]

### Added
- link to conda-forge as installation source for gdrive

## [2020.07.0]

### Fixed
- Signature of `update_file`
- Variable name `file_id` when formatting urls

### Changed
- Now uses Avro-RPC [YEP-107](https://yeps.yaq.fyi/107/)
- Uses Flit for distribution

## [2020.05.0]

### Added
- added changelog
- Use format strings instead of assuming concatenation
- added mypy to precommit
- added daemon-level version, see [YEP-105](https://yeps.yaq.fyi/105/)

### Changed
- from now on, yaqd-gdrive will use calendar based versioning
- cleanup repository
- refactor gitlab-ci
- Use daemon level loggers, see [YEP-106](https://yeps.yaq.fyi/106)
- updated readme

## [0.2.0]

### Fixed
- fixed import

## [0.1.1]

### Fixed
- make find_packages work

## [0.1.0]

### Added
- initial release

[Unreleased]: https://gitlab.com/yaq/yaqd-gdrive/-/compare/v2020.12.0...master
[2020.12.0]: https://gitlab.com/yaq/yaqd-gdrive/-/compare/v2020.07.0...v2020.12.0
[2020.07.0]: https://gitlab.com/yaq/yaqd-gdrive/-/compare/v2020.05.0...v2020.07.0
[2020.05.0]: https://gitlab.com/yaq/yaqd-gdrive/-/compare/v0.2.0...v2020.05.0
[0.2.0]: https://gitlab.com/yaq/yaqd-gdrive/-/compare/v0.1.1...v0.2.0
[0.1.1]: https://gitlab.com/yaq/yaqd-gdrive/-/compare/v0.1.0...v0.1.1
[0.1.0]: https://gitlab.com/yaq/yaqd-gdrive/-/tags/v0.1.0
