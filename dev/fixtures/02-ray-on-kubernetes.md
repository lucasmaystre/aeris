# Running a Ray cluster on Kubernetes
Tags: #infra/kubernetes, #infra/ray

A long how-to, with headings, a table and code in several languages.

## Prerequisites

You need `kubectl`, `helm` and access to a cluster with GPU nodes. Check the context first:

```bash
kubectl config current-context
helm repo add kuberay https://ray-project.github.io/kuberay-helm/
helm install kuberay-operator kuberay/kuberay-operator --version 1.4.2
```

## Cluster spec

Pin the head node to CPU nodes and the workers to GPU nodes:

```yaml
apiVersion: ray.io/v1
kind: RayCluster
metadata:
  name: research
spec:
  headGroupSpec:
    template:
      spec:
        nodeSelector:
          feature.node.kubernetes.io/cpu-cpuid.AVX2: "true"
  workerGroupSpecs:
    - groupName: gpu
      replicas: 4
```

## Submitting a job

```python
import ray

ray.init(address="ray://research-head-svc:10001")

@ray.remote(num_gpus=1)
def score(batch: list[str]) -> list[float]:
    return [len(text) / 100 for text in batch]

print(ray.get([score.remote(["a", "bb"]) for _ in range(8)]))
```

## Sizing

| Workload | Workers | GPUs each | Notes |
|---|---|---|---|
| Evaluation | 4 | 1 | Fits in a few hours |
| Best-of-N sampling | 16 | 8 | Needs the canonical priority |
| Fine-tuning | 8 | 8 | Checkpoint every 500 steps |

## Troubleshooting

If pods stay `Pending`, describe them: it's nearly always a node selector or a quota. Logs live at
`/tmp/ray/session_latest/logs` on the head node.
