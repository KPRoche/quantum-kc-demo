# Deploying Quantum KC Demo with KubeStellar Console

This guide covers deploying the [quantum-kc-demo](https://github.com/KPRoche/quantum-kc-demo) workload in your Kubernetes cluster and connecting it to KubeStellar Console.

## Overview

The quantum-kc-demo is a containerized quantum computing simulator with a REST API. KubeStellar Console provides UI cards to interact with it (circuit execution, results visualization, SVG display). The console communicates with the quantum service via the `QUANTUM_SERVICE_URL` environment variable.

## Prerequisites

- Kubernetes cluster (kind, OpenShift, EKS, GKE, AKS, or bare metal)
- `kubectl` configured to access your cluster
- KubeStellar Console running locally or on a reachable network

## Step 1: Deploy quantum-kc-demo to Your Cluster

### Create the Quantum Namespace

```bash
kubectl create namespace quantum
```

### Get the Deployment Manifests

The quantum-kc-demo repo includes ready-to-use Kubernetes manifests in `k8s/`:

```bash
cd quantum-kc-demo
ls k8s/
# Output: deployment.yaml  service.yaml  servicemonitor.yaml
```

### Customize the Service for Your Cluster Type

The service type must match your cluster environment. Edit or apply the appropriate manifest:

#### For kind (Development/Demo)

Use the default `NodePort` service (port 30500). **Important:** Your kind cluster must be created with port mapping:

```yaml
# kind-config.yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
  extraPortMappings:
  - containerPort: 30500
    hostPort: 30500
    protocol: TCP
```

Create the cluster with this config:
```bash
kind create cluster --config kind-config.yaml
```

Then apply the manifests:
```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

The service is reachable at `http://localhost:30500`.

#### For OpenShift / OCM

Replace `NodePort` with `ClusterIP` + `Route`:

```bash
# Edit service.yaml: change type from NodePort to ClusterIP
kubectl patch service quantum-kc-demo -n quantum --type merge -p '{"spec":{"type":"ClusterIP"}}'

# Create an OpenShift Route
cat <<EOF | kubectl apply -f -
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: quantum-kc-demo
  namespace: quantum
spec:
  host: quantum-kc-demo.apps.<your-cluster-domain>
  to:
    kind: Service
    name: quantum-kc-demo
  port:
    targetPort: 5000
EOF
```

The service is reachable at the route hostname (e.g., `http://quantum-kc-demo.apps.your-cluster.com`).

#### For Cloud (EKS, GKE, AKS) or Bare Metal

Use `LoadBalancer` service:

```bash
# Edit service.yaml: change type from NodePort to LoadBalancer
kubectl patch service quantum-kc-demo -n quantum --type merge -p '{"spec":{"type":"LoadBalancer"}}'

# Get the external IP/hostname
kubectl get svc -n quantum quantum-kc-demo
# Example output:
# NAME                TYPE           CLUSTER-IP      EXTERNAL-IP                                     PORT(S)          AGE
# quantum-kc-demo     LoadBalancer   10.0.0.123      a1b2c3d4-123456789.us-west-2.elb.amazonaws.com  80:30000/TCP     2m
```

The service is reachable at the external IP or hostname (e.g., `http://a1b2c3d4-123456789.us-west-2.elb.amazonaws.com`).

Alternatively, use an `Ingress` resource if your cluster has an `IngressController`.

### Verify Deployment

Wait for the pod to be ready:

```bash
kubectl wait --for=condition=Ready pod -l app=quantum-kc-demo -n quantum --timeout=300s

# Check the pod is running
kubectl get pods -n quantum
kubectl logs -n quantum -l app=quantum-kc-demo
```

Test the API endpoint:

```bash
# For kind/OpenShift/Cloud (adjust URL to your service address)
curl http://localhost:30500/api/status
# Expected response: {"running": false, "last_result": null, ...}
```

## Step 2: Configure KubeStellar Console Backend

### Set the QUANTUM_SERVICE_URL Environment Variable

The console backend needs to know where to reach the quantum service. Set this before starting the backend:

```bash
# For kind (local development)
export QUANTUM_SERVICE_URL=http://localhost:30500

# For cloud LoadBalancer (example)
export QUANTUM_SERVICE_URL=http://a1b2c3d4-123456789.us-west-2.elb.amazonaws.com

# For OpenShift Route
export QUANTUM_SERVICE_URL=http://quantum-kc-demo.apps.your-cluster.com
```

If not set, the console backend defaults to `http://localhost:5000` (for local development with port-forward).

### Start the Console Backend

```bash
# Option 1: Development mode (no OAuth)
./start-dev.sh

# Option 2: With GitHub OAuth
./startup-oauth.sh
```

The backend runs on `localhost:8080` and uses the `QUANTUM_SERVICE_URL` to proxy quantum API calls.

## Step 3: Access Quantum Cards in the Console

1. Open the console at `http://localhost:5174`
2. Create or open a dashboard
3. Add quantum cards:
   - **Quantum Control Panel** — Execute circuits, select backends, manage loop mode
   - **Quantum Circuit Viewer** — View circuit execution results as SVG
   - **Quantum Status** — Monitor current execution status
   - **Quantum Results** — View detailed measurement results

## Configuration Options

### Quantum Deployment Environment Variables

Edit `k8s/deployment.yaml` to customize the quantum service:

| Variable | Default | Options | Purpose |
|----------|---------|---------|---------|
| `QUANTUM_BACKEND` | `local` | `local`, `aer`, `aer_noise` | Simulator backend (no credentials needed) |
| `QUANTUM_QUBITS` | `5` | `5`, `12`, `16` | Number of qubits in the circuit |
| `FLASK_ENV` | `production` | `production`, `development` | Flask environment |
| `TZ` | `America/Los_Angeles` | Any valid timezone | Container timezone |

Example: To use a 12-qubit hex circuit:

```bash
kubectl set env deployment/quantum-kc-demo -n quantum QUANTUM_QUBITS=12
```

### Console Backend Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `QUANTUM_SERVICE_URL` | `http://localhost:5000` | URL to reach quantum service API |

## Troubleshooting

### Console Cannot Reach Quantum Service

**Error:** `Quantum service unavailable` when executing circuits

**Solutions:**
1. Verify the service is running: `kubectl get svc -n quantum`
2. Check the pod is ready: `kubectl get pods -n quantum`
3. Test direct access: `curl $QUANTUM_SERVICE_URL/api/status`
4. Verify `QUANTUM_SERVICE_URL` is set correctly in console backend
5. Check firewall/network policies allow console → quantum communication

### Pod Keeps Crashing

**Error:** Pod in `CrashLoopBackOff`

**Solutions:**
1. Check pod logs: `kubectl logs -n quantum -l app=quantum-kc-demo`
2. Verify resource limits are sufficient (default: 512Mi mem, 250m CPU)
3. Increase limits in `deployment.yaml` if needed:
   ```yaml
   resources:
     requests:
       memory: "1Gi"
       cpu: "500m"
     limits:
       memory: "4Gi"
       cpu: "2000m"
   ```

### Circuit Execution Times Out

**Error:** Circuits take too long or fail to execute

**Solutions:**
1. Reduce circuit complexity: Use `QUANTUM_QUBITS=5` instead of 16
2. Reduce shot count in Quantum Control Panel (1-100 shots for testing)
3. Check cluster CPU/memory availability: `kubectl top nodes`
4. Verify backend is local simulator, not waiting for IBM Quantum credentials

### Service Not Accessible from Outside Cluster

For kind with NodePort:
- Verify kind cluster created with port mapping at 30500
- Check port isn't already in use: `lsof -i :30500` or `netstat -tuln | grep 30500`

For cloud LoadBalancer:
- Wait for external IP assignment (can take 1-2 minutes)
- Check security groups/firewall allow traffic to port 80/5000
- Verify LoadBalancer service endpoint is correct

## Advanced: Using Custom QASM Circuits

The Quantum Control Panel card allows uploading custom QASM files. These are persisted via the `/api/qasm/file` endpoint.

1. In the Console, open Quantum Control Panel
2. Paste or upload your QASM circuit
3. Click "Execute" to run it

The custom circuit is saved on the quantum service and can be selected in subsequent executions.

## Advanced: Port Forwarding (Alternative to Service Configuration)

If you can't expose the service via NodePort/LoadBalancer/Route, use `kubectl port-forward`:

```bash
kubectl port-forward -n quantum svc/quantum-kc-demo 5000:5000 &
export QUANTUM_SERVICE_URL=http://localhost:5000
```

This bridges the service to `localhost:5000`. Note: Port forwarding is intended for development only; use proper service exposure for production.

## Next Steps

- Explore quantum circuit execution and results visualization
- Check out the [quantum-kc-demo API documentation](https://github.com/KPRoche/quantum-kc-demo/blob/main/API_ENDPOINTS.md)
- For production deployments, consider:
  - Using HTTPS with ingress TLS certificates
  - Adding authentication/authorization
  - Enabling monitoring (Prometheus metrics exported on `/metrics`)
  - Setting resource quotas in the `quantum` namespace

## References

- [quantum-kc-demo Repository](https://github.com/KPRoche/quantum-kc-demo)
- [quantum-kc-demo Deployment Guide](https://github.com/KPRoche/quantum-kc-demo/blob/main/DEPLOYMENT.md)
- [KubeStellar Console Documentation](https://github.com/kubestellar/console)
