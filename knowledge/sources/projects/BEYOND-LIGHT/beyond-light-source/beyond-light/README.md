# Java source reference and regression suite

This directory preserves the original Java 21 scientific and engineering implementations while their browser counterparts are audited and ported. **It is not the Beyond-Light website runtime and is not deployed as a service.**

The public application is the static browser site in `../../docs/`. It does not call this Java source, start an HTTP endpoint, require SnapDeploy, or need a container. The Dockerfile and local server launcher were intentionally removed to prevent treating this source tree as a hosted application.

## Source areas

The Java source retains mathematical, physics, relativity, materials, feasibility, technology-design, uncertainty, dataset, benchmark, and research implementations. These files are references for comparison and regression checks. Browser coverage is tracked in `../../docs/catalog.json`; a partial browser port must not be described as exact parity.

## Run regression checks

Requirements: JDK 21 and Gradle 8.10.2.

From this directory:

```sh
./check.sh
```

Or:

```sh
gradle --no-daemon verifyCore verifyIntegrationCore
```

These commands execute tests only. There is no Gradle `run` task and no supported Java server deployment path.

## Scientific limits

A numerical result is valid only within the implemented equations, supplied values, numerical tolerances, and stated assumptions. A passing analytical benchmark is not experimental validation, engineering certification, or proof that a machine can be built.
