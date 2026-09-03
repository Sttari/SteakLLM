# 0010 — The admin door is the tailnet; the interior walls are default-deny NetworkPolicies

Status: proposed (accepted when 8.9 closes the interim endpoint and 8.10's blocked path is proven)
Date: 2026-09-03

## Context

Step 8 put a dozen services on one cluster: some must be reached by a human (Grafana, Argo CD, Open WebUI, the gateway), most must be reached only by other services, and none must be reached from the internet until Step 12's public door. Kubernetes gives every pod a routable address and, by default, lets every pod talk to every other pod. Two doors and a set of walls are needed, and each must be provable.

## Decision

1. **The admin door is Tailscale.** The Tailscale operator (deployed by Argo, its OAuth client from Secrets Manager) exposes chosen Services on the tailnet — a WireGuard mesh between Thomas's devices and the cluster's proxies — and a `Connector` advertises the VPC's range so `kubectl` works from the laptop. Nothing else is exposed: no NodePort, no LoadBalancer, no public Ingress; `aws elbv2 describe-load-balancers` staying empty is a done-when. Once the tailnet works, the cluster's API endpoint becomes private-only and Step 7's `/32` interim ends.
2. **The interior walls are NetworkPolicies, default-deny in every application namespace** (`steakllm`, `kafka`, `qdrant`, `ollama`, `open-webui`), enforced by the VPC CNI's network-policy agent (off by default on EKS — turned on in `infra/eks`), with DNS granted everywhere and every other path opened by a named policy: gateway and workers → Kafka, Qdrant, Ollama, AWS over the NAT; Kafka, Qdrant, Ollama ← the `steakllm` namespace and Prometheus; Open WebUI → the gateway only; the Tailscale proxies → their targets. Platform namespaces (`argocd`, `monitoring`, `logging`, `external-secrets`, `kube-system`, `tailscale`) are not walled in Step 8: their pods are the ones that must reach everything (Prometheus scrapes, Alloy tails, Argo applies), and walling them is a Step 10 hardening item with its own drill.
3. **Pod Security profiles per namespace:** `restricted` where a chart can run that way (`steakllm`, `qdrant`, `ollama`, `external-secrets`), `baseline` where a component needs a little more (`kafka`, `open-webui`, `tailscale`), `privileged` only where the node itself must be touched (`monitoring` for node-exporter, `logging` for the log tailer), with `warn`/`audit` at `baseline` there so anything else that oversteps is logged (Incident 28).

## Alternatives

- **A bastion host or a VPN gateway for admin access.** A machine to patch and a port to guard. Rejected: the tailnet needs no inbound port, no public address, and works from any of Thomas's devices; the operator's proxies are pods Argo manages like everything else.
- **`kubectl port-forward` forever.** Works today (it is how 8.4–8.8 were verified) and needs the API endpoint reachable, which is the interim `/32` this ADR closes. Rejected as the steady state: one address, one laptop, one command per service.
- **Calico or Cilium for NetworkPolicy.** Richer policies (DNS-name egress, layer 7). Rejected for now: one more CNI to operate; the VPC CNI's agent enforces the standard API and is the AWS-supported path. Revisit if egress-by-domain is ever needed (Bedrock and S3 by IP block is coarse but works).
- **Allow-by-default with a few denies.** Rejected: a museum with open doors and a few locked cases; a new pod would be reachable by everything until someone remembers to lock it.
- **Walling the platform namespaces too, in Step 8.** Rejected for now: the scrape/tail/apply paths would each need a policy written before any could be tested; done as a Step 10 drill with the blocked-path proof repeated.

## Consequences

- A new service needs two lines of YAML before it can talk: an egress policy for what it calls and an ingress policy on what it calls. This is the point.
- Kubelet probes and the Tailscale proxies cross namespace boundaries; the policies name them. If a probe ever fails after a policy change, the policy is the first suspect.
- The tailnet's ACL is a second place where access is defined (Tailscale's policy file, outside git); Step 12 records it beside the repo.
- Until 8.9 is done the admin path is port-forward through the `/32`, and the laptop's address must match the variable (it drifted once on Sep 3).
