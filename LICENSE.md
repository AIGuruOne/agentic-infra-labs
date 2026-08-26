# Licence, in detail

The canonical licence text is in [`LICENSE`](LICENSE) — plain MIT, which is what
GitHub reads. This file adds the third-party notices, the trademark terms, and
the scope notes that do not belong in a bare licence file.

## MIT License

Copyright © 2026 Keyom Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

## What this covers

Everything in this repository: the labs, the agent, the MCP servers, the
guardrails, the fault scripts, the runbook corpus, the tests, and the
documentation. Use it, change it, ship it inside your own systems, teach from
it. No attribution beyond the notice above is required, and none is expected.

## Third-party components

**`observability/metrics-server.yaml`** is not ours. It is vendored from
[kubernetes-sigs/metrics-server](https://github.com/kubernetes-sigs/metrics-server)
v0.8.0, Copyright The Kubernetes Authors, licensed under the **Apache License,
Version 2.0** — <http://www.apache.org/licenses/LICENSE-2.0>. One line was
added to the container args (`--kubelet-insecure-tls`), noted in the file
header. That file remains under Apache 2.0; the MIT grant above does not
relicense it.

Everything else here is original work.

The Python dependencies in `requirements.txt` and `alt/langgraph/requirements.txt`
are installed from PyPI at their own licences and are not redistributed here.
Container images (`prom/prometheus`, `python`) are pulled from their registries
under their own terms.

## Trademarks

**AI Guru®** is a registered trademark of Keyom Inc. The MIT licence above
grants rights to the software, not to the trademark. You may fork this
repository and build on it freely; please do not use the AI Guru® name or logo
in a way that suggests your derivative work is produced or endorsed by us.

## The session recording

This licence covers the **code and documentation in this repository**. It does
not cover the recorded video of the live session, which is a Packt product and
is distributed under Packt's own terms.

## No warranty, and one thing worth saying plainly

Beyond the warranty disclaimer above: this is teaching material demonstrating
patterns for AI agents that act on infrastructure.

The guardrails here — read-only defaults, approval gates, dry runs, scoped
credentials, audit logging — are illustrative of an approach. They are not a
security product, and the only one of the four enforced outside the agent's own
process is the Kubernetes RBAC. Review, adapt, and test anything you carry into
a production environment against your own requirements and your own security
review.

---

*AI Guru® · [aiguru.one](https://aiguru.one) · © 2026 Keyom Inc.*
