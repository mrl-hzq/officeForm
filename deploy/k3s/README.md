# officeForm on K3s and Zeabur

The public request flow is:

```text
Browser
  |  https://officeform.duckdns.org
  v
DuckDNS (A record: 43.134.43.225)
  |
  v
Zeabur ingress controller (public ports 80/443)
  |  matches the officeform.duckdns.org Ingress rule
  v
K3s Service: officeform:3000 (stable internal address)
  |
  v
officeForm Pod (container created from the registry image)
  |-- /app/formOri   -> immutable templates included in the image
  |-- /app/generated -> officeform-generated PersistentVolumeClaim
  `-- /app/others    -> officeform-others PersistentVolumeClaim
```

The image delivery flow is separate from the public request flow:

```text
Windows development PC
  |  docker build + docker push over Tailscale
  v
Registry: 100.95.211.72:5000
  |  K3s containerd pulls through the registries.yaml HTTP endpoint
  v
officeForm Pod
```

## What each K3s object does

- `Deployment`: declares the image, environment source, volume mounts, health checks, and that one officeForm Pod must remain running.
- `Pod`: the running officeForm container. K3s replaces it if it crashes.
- `Service`: provides a stable internal address for the Pod, even after the Pod is replaced.
- `Ingress`: tells Zeabur's ingress controller to send requests for `officeform.duckdns.org` to the Service.
- `PersistentVolumeClaim` (PVC): requests durable storage from K3s's `local-path` StorageClass.
- `PersistentVolume` (PV): the actual directory allocated on this server for a PVC, normally below `/var/lib/rancher/k3s/storage/`.

The PVC data survives Pod replacement and image upgrades. It does not survive loss of the server disk, so it still requires backups. Deleting a PVC may also delete its associated local data.

## Server environment secret

Kubernetes does not automatically read a Docker Compose `.env` file. Store the production values in a server-only file such as `/opt/officeform/.env`:

```dotenv
TZ=Asia/Kuala_Lumpur
ENVIRONMENT=production
APP_HOST=0.0.0.0
APP_PORT=3000
DB_USER=officeform
DB_PASSWORD=replace-with-database-password
DB_SERVER=replace-with-mysql-host
DB_PORT=3306
DB_SCHEMA=officeform
JWT_SECRET_KEY=replace-with-a-long-random-value
AUTH_SHARED_PASSWORD=abcd1234
```

Protect it and create/update the Kubernetes Secret:

```bash
sudo chmod 600 /opt/officeform/.env
sudo k3s kubectl create namespace officeform --dry-run=client -o yaml | sudo k3s kubectl apply -f -
sudo k3s kubectl create secret generic officeform-env \
  --namespace officeform \
  --from-env-file=/opt/officeform/.env \
  --dry-run=client -o yaml | sudo k3s kubectl apply -f -
```

Changing `.env` does not automatically update a running Pod. Re-run the Secret command and restart the Deployment:

```bash
sudo k3s kubectl rollout restart deployment/officeform --namespace officeform
```

## Deploy

After image `1.0.1` has been built and pushed:

```bash
sudo k3s kubectl apply -f deploy/k3s/officeform.yaml
sudo k3s kubectl get pods,pvc,service,ingress --namespace officeform
sudo k3s kubectl rollout status deployment/officeform --namespace officeform --timeout=180s
```

Do not expose container port `3000` with a public NodePort. The ClusterIP Service and Ingress are the intended path.
