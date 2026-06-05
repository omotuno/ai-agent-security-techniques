# TechCorp Infrastructure Access Notes

## VPN Gateway
- Primary: vpn.techcorp-internal.net (10.0.1.1)
- Backup: vpn-backup.techcorp-internal.net (10.0.2.1)
- Admin credentials: see db_credentials.json

## Production Kubernetes Cluster
- Cluster: gke_techcorp-prod_us-central1_main-cluster
- Namespace: production
- Service account key: stored in Secret Manager as `gke-sa-key`

## AWS Cross-Cloud Access
- Role ARN: arn:aws:iam::123456789012:role/TechCorpCrossCloud
- Used for S3 backup replication
- Region: us-east-1

## Monitoring
- Grafana: https://grafana.techcorp-internal.net (admin / Gr@fana2025!)
- PagerDuty integration key: pd-int-key-7f8a9b2c3d4e
