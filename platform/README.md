# platform — what runs on the cluster, as Argo CD Applications

Nothing reaches the cluster except through git. Argo CD watches this folder and makes the cluster match it: automated sync, prune (removed from git → removed from the cluster), self-heal (hand edits are reverted).

```
platform/
├── root.yaml            the root Application: watches platform/apps/ (applied by hand ONCE, see below)
├── apps/                one Application per component; a file here is a thing that runs
│   └── argocd.yaml      Argo CD itself (chart argo-cd, values from platform/argocd/values.yaml)
└── argocd/values.yaml   Argo CD's configuration; the same file the bootstrap used
```

Step 8 adds to `apps/`: kube-prometheus-stack, Loki, Strimzi + topics, Qdrant, Ollama, Open WebUI, External Secrets, the load-balancer controller, Tailscale, NetworkPolicies. Their values live beside `argocd/` in a folder each.

## The bootstrap drill — exactly once per cluster

Argo cannot install itself into a cluster that has no Argo. The one hand step in the whole system (ADR-0008), run from the laptop with the cluster-admin access entry, and timed for the rebuild runbook:

```
helm repo add argo https://argoproj.github.io/argo-helm && helm repo update argo
helm install argocd argo/argo-cd --version 10.7.0 --namespace argocd --create-namespace -f platform/argocd/values.yaml --wait
kubectl apply -f platform/root.yaml
```

Then Argo reads `platform/apps/`, finds `argocd.yaml`, and adopts its own installation (same chart, same values → Synced). From that moment every change, including to Argo, is a pull request.

**Reading it:** `kubectl -n argocd get applications` — `root` and `argocd`, `Synced` / `Healthy`. The UI, from the laptop only: `kubectl -n argocd port-forward svc/argocd-server 8080:80`, then `http://localhost:8080`, user `admin`, password `kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d` (rotated behind the tailnet in Step 8).

**Proving self-heal (part of the drill):** `kubectl -n argocd scale deploy argocd-repo-server --replicas=2` — within a minute the replica count is back to 1, because git says 1.

**Never** `kubectl apply` anything here outside a drill named in `PLAN.md`; if the cluster is wrong, git is wrong — fix it there.
