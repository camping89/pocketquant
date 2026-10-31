#!/usr/bin/env bash
# Lease owners and whether each owner is a running container of its compose service.
# usage: leases.sh -> worker=<owner> trader=<owner> unexpired=<n> owners_match=<yes|no>
cd "$(dirname "$(readlink -f "$0")")/.." || exit 1
dc() { docker compose -f compose.prod.yml --env-file .env "$@"; }
hosts() { for c in $(dc ps -q "$1"); do docker inspect -f '{{.Config.Hostname}}' "$c"; done; }
t=$(dc ps -q trader | head -1)
read -r w tr n < <(docker exec "$t" python -c 'from datetime import UTC, datetime
from pymongo import MongoClient
from pocketquant.core.config import get_settings
s = get_settings(); db = MongoClient(str(s.mongodb_url), tz_aware=True)[s.mongodb_database]
d = {x["name"]: x for x in db.leases.find()}; now = datetime.now(UTC)
print(d.get("worker", {}).get("owner", "none"), d.get("trader", {}).get("owner", "none"), sum(x["expires_at"] > now for x in d.values()))' 2>/dev/null || echo "none none ?")
m=yes
hosts worker | grep -qx "${w%%:*}" || m=no
hosts trader | grep -qx "${tr%%:*}" || m=no
echo "worker=$w trader=$tr unexpired=$n owners_match=$m"
