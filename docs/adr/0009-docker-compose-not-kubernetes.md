# ADR-0009: Docker Compose for deployment, not Kubernetes

**Status:** Accepted (MVP)

**Decision:** The entire stack (Postgres, Qdrant, API, Web) is defined in a
single `docker-compose.yml` and started with `docker compose up`.

**Alternatives considered:** Kubernetes + Helm + Terraform is the
production target described in the full enterprise SRS, appropriate for
multi-instance, autoscaled, multi-environment deployment.

**Why this wins for a portfolio MVP:** the audience for this repository —
a recruiter or reviewer — needs to go from `git clone` to a running product
in one command, with no cloud account, cluster, or cost. Kubernetes
manifests with a single replica of everything would be operational
complexity with no corresponding benefit at this stage.

**MVP impact:** no autoscaling, no rolling deploys, single-host only.

**Revisit when:** there is a real deployment target (staging/production
cloud environment) that needs more than one instance of any service —
Phase 2 introduces Terraform + Kubernetes per the enterprise architecture.
