# Changelog

## [1.3.0](https://github.com/fishaudio/fish-audio-python/compare/fish-audio-sdk-v1.2.0...fish-audio-sdk-v1.3.0) (2026-02-21)


### Features

* add advanced generation parameters to TTSConfig and update related tests ([#85](https://github.com/fishaudio/fish-audio-python/issues/85)) ([6cb173c](https://github.com/fishaudio/fish-audio-python/commit/6cb173c1808de8f15fede8d194408f158bf3ae51))
* add Dependabot configuration for daily updates ([07884da](https://github.com/fishaudio/fish-audio-python/commit/07884dafba09112c676cc97075f5eb56cfaf23ee))
* Add py.typed for better type hinting ([#27](https://github.com/fishaudio/fish-audio-python/issues/27)) ([a51d0b9](https://github.com/fishaudio/fish-audio-python/commit/a51d0b9c399421a5ff31eb9e1206d63d4defe6d0))
* add release token to release-please action in python.yml ([#106](https://github.com/fishaudio/fish-audio-python/issues/106)) ([bf53815](https://github.com/fishaudio/fish-audio-python/commit/bf53815221a357cb5627cbaa38dbf937ce8671e3))
* add release-please configuration and version manifest ([#105](https://github.com/fishaudio/fish-audio-python/issues/105)) ([de11000](https://github.com/fishaudio/fish-audio-python/commit/de110000ba66a02602264c5140fd94a00713e0aa))
* add tests for testing all wss model backends ([#53](https://github.com/fishaudio/fish-audio-python/issues/53)) ([87e6b65](https://github.com/fishaudio/fish-audio-python/commit/87e6b65511c29aaef37c07e876db2e75c18c4b7e))
* add WebSocketErr exception to the API ([#28](https://github.com/fishaudio/fish-audio-python/issues/28)) ([864863c](https://github.com/fishaudio/fish-audio-python/commit/864863c7bc35a22b7a7b602c7c88febf6bcf5767))
* add WebSocketOptions for configurable WebSocket connections ([#48](https://github.com/fishaudio/fish-audio-python/issues/48)) ([6f9ab7b](https://github.com/fishaudio/fish-audio-python/commit/6f9ab7b3f480b8e1b24504b3116d27f413e553ae))
* api reference docs pipeline ([#30](https://github.com/fishaudio/fish-audio-python/issues/30)) ([c1153d8](https://github.com/fishaudio/fish-audio-python/commit/c1153d8c1d2719f73b9d0540d6ae958ced070142))
* implement v1 sdk ([#29](https://github.com/fishaudio/fish-audio-python/issues/29)) ([54bc101](https://github.com/fishaudio/fish-audio-python/commit/54bc10162b97fa366eafb214611ebc743e64a72c))
* integrate poe for task management in CI/CD workflows ([#110](https://github.com/fishaudio/fish-audio-python/issues/110)) ([daf00fe](https://github.com/fishaudio/fish-audio-python/commit/daf00fe4f10b96e4a005351e78f08a17f543052f))
* mark all integration tests as flaky with auto-retry ([#87](https://github.com/fishaudio/fish-audio-python/issues/87)) ([3c2f829](https://github.com/fishaudio/fish-audio-python/commit/3c2f8296ea493f06d10e140a393542b9208b7e54))
* model 1 6 supported and more control parameters ([#20](https://github.com/fishaudio/fish-audio-python/issues/20)) ([34c7866](https://github.com/fishaudio/fish-audio-python/commit/34c7866bcf5ff8e812645ab98b469994fb573031))
* prepare v1.0.0 release ([#42](https://github.com/fishaudio/fish-audio-python/issues/42)) ([88ac9b5](https://github.com/fishaudio/fish-audio-python/commit/88ac9b5f1fafa3907891201215ca3361ade885be))
* QoL and account related APIs ([1eeb4d3](https://github.com/fishaudio/fish-audio-python/commit/1eeb4d3d538062ed1fd425a2bac81ccca52507a7))
* replace mypy with ty ([#73](https://github.com/fishaudio/fish-audio-python/issues/73)) ([3ac2b9d](https://github.com/fishaudio/fish-audio-python/commit/3ac2b9daf4b3de887adba3d839fc4005cfd7a5d0))
* update environment for release workflow in python.yml ([#32](https://github.com/fishaudio/fish-audio-python/issues/32)) ([501bef6](https://github.com/fishaudio/fish-audio-python/commit/501bef6905094926d2051a552be8e518b2684840))
* update project description for clarity ([773183c](https://github.com/fishaudio/fish-audio-python/commit/773183c4896de0bcffe963411b1c8a0c7ff8d3ad))


### Bug Fixes

* allow non `s` prefixed models to fail websocket integration tests ([#71](https://github.com/fishaudio/fish-audio-python/issues/71)) ([6a2a289](https://github.com/fishaudio/fish-audio-python/commit/6a2a28924e61faa14fd85fac9d1524ca1048bad3))
* correct visibility option ([#97](https://github.com/fishaudio/fish-audio-python/issues/97)) ([69572df](https://github.com/fishaudio/fish-audio-python/commit/69572dfaef5db7b9b2c823ded93d4f80a0a74a7d))
* ensure user agent is consistent across http/websockets ([#65](https://github.com/fishaudio/fish-audio-python/issues/65)) ([203ee04](https://github.com/fishaudio/fish-audio-python/commit/203ee04bcaef9421c46334bdd4a0917105482a27))
* rename the API parameter self to self_only to avoid python conflict ([#21](https://github.com/fishaudio/fish-audio-python/issues/21)) ([ff8aa73](https://github.com/fishaudio/fish-audio-python/commit/ff8aa7365c1fd1ecf7dfc27af5b48ae890f503a6))
* update python banner image URL in README ([#72](https://github.com/fishaudio/fish-audio-python/issues/72)) ([ac5f010](https://github.com/fishaudio/fish-audio-python/commit/ac5f010ff4a5fd30bce094586ba1305273bffeb8))


### Documentation

* add contributing guidelines to CONTRIBUTING.md ([#50](https://github.com/fishaudio/fish-audio-python/issues/50)) [skip ci] ([e1b904e](https://github.com/fishaudio/fish-audio-python/commit/e1b904ee631c243d684c4a9fc0319b57892eef84))
* update README to clarify changes in PyPI versioning for Fish Audio Python SDK ([#45](https://github.com/fishaudio/fish-audio-python/issues/45)) [skip ci] ([0f97f6f](https://github.com/fishaudio/fish-audio-python/commit/0f97f6fa835df4779c758ef1c9f278625c19eaa8))
* use GitHub markdown for version notice ([#46](https://github.com/fishaudio/fish-audio-python/issues/46)) [skip ci] ([4e39d0c](https://github.com/fishaudio/fish-audio-python/commit/4e39d0cd04bee7fcac2ecc176814c417a49869b6))
