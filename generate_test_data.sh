#!/usr/bin/env bash

set -eux

read TOKEN PROJECT_ID <<<$(openstack token issue -f value -c id -c project_id)
export TOKEN
export PROJECT_ID
NOVA_ENDPOINT=$(openstack endpoint list --interface public --service compute -f value -c URL)
NOVA_ENDPOINT=${NOVA_ENDPOINT%'$(tenant_id)s'}$PROJECT_ID
export NOVA_ENDPOINT
for user in $(openstack user list -f value -c ID) ; do
    data=$(cat <<-EOS
{
    "keypair": {
      "name": "$(uuidgen)",
      "type": "ssh",
      "user_id": "${user}"
    }
}
EOS
)
    curl -i -H "X-Auth-Token: $TOKEN" -H 'Content-Type: application/json' -H 'X-OpenStack-Nova-API-Version: 2.12' -X POST -d "$data" ${NOVA_ENDPOINT}/os-keypairs
    data=$(cat <<-EOS
{
    "keypair": {
      "name": "$(uuidgen)",
      "type": "ssh",
      "user_id": "${user}"
    }
}
EOS
)
    curl -i -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" -H 'X-OpenStack-Nova-API-Version: 2.12' -X POST -d "$data" ${NOVA_ENDPOINT}/os-keypairs
    data=$(cat <<-EOS
{
    "keypair": {
      "name": "$(uuidgen)",
      "type": "x509",
      "user_id": "${user}"
    }
}
EOS
)
    curl -i -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" -H 'X-OpenStack-Nova-API-Version: 2.12' -X POST -d "$data" ${NOVA_ENDPOINT}/os-keypairs
done

for project in $(seq 1 3000) ; do
    openstack project create $project
done

for project in $(openstack project list -f value -c ID) ; do
    data=$(cat <<-EOS
{
    "quota_set": {
        "cores": 2147483647,
        "fixed_ips": 2147483647,
        "floating_ips": 2147483647,
        "injected_file_content_bytes": 2147483647,
        "injected_file_path_bytes": 2147483647,
        "instances": 2147483647,
        "key_pairs": 2147483647,
        "metadata_items": 2147483647,
        "ram": 2147483647,
        "security_group_rules": 2147483647,
        "security_groups": 2147483647,
        "server_groups": 2147483647,
        "server_group_members": 2147483647
    }
}
EOS
)
    curl -i -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" -H 'X-OpenStack-Nova-API-Version: 2.12' -X PUT -d "$data" ${NOVA_ENDPOINT}/os-quota-sets/${project}
done

export DEFAULT_PROJECT_ID=$(openstack project show openstack -f value -c id)
for user in $(openstack user list -f value -c ID) ; do
    data=$(cat <<-EOS
{
    "quota_set": {
        "cores": 20,
        "fixed_ips": 10,
        "floating_ips": 40,
        "injected_file_content_bytes": 70,
        "injected_file_path_bytes": 40,
        "instances": 80,
        "key_pairs": 30,
        "metadata_items": 60,
        "ram": 1024,
        "security_group_rules": 70,
        "security_groups": 20,
        "server_groups": 10,
        "server_group_members": 40
    }
}
EOS
)
    PROJECTS=$(openstack project list -f value -c ID)
    RANDOM_PROJECT=$( echo -e "$PROJECTS" | sort -R | head -1 )
    curl -i -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" -H 'X-OpenStack-Nova-API-Version: 2.12' -X PUT -d "$data" ${NOVA_ENDPOINT}/os-quota-sets/${RANDOM_PROJECT}?user_id=${user}
    RANDOM_PROJECT=$( echo -e "$PROJECTS" | sort -R | head -1 )
    curl -i -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" -H 'X-OpenStack-Nova-API-Version: 2.12' -X PUT -d "$data" ${NOVA_ENDPOINT}/os-quota-sets/${RANDOM_PROJECT}?user_id=${user}
    RANDOM_PROJECT=$( echo -e "$PROJECTS" | sort -R | head -1 )
    curl -i -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" -H 'X-OpenStack-Nova-API-Version: 2.12' -X PUT -d "$data" ${NOVA_ENDPOINT}/os-quota-sets/${RANDOM_PROJECT}?user_id=${user}
    curl -i -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" -H 'X-OpenStack-Nova-API-Version: 2.12' -X PUT -d "$data" ${NOVA_ENDPOINT}/os-quota-sets/${DEFAULT_PROJECT_ID}?user_id=${user}
done


NEUTRON_ENDPOINT="$(openstack endpoint list --interface public --service network -f value -c URL)/v2.0"
export NEUTRON_ENDPOINT
for project in $(openstack project list -f value -c ID) ; do
    data=$(cat <<-EOS
{
    "quota": {
        "floatingip": 2147483647,
        "security_group_rule": 2147483647,
        "security_group": 2147483647,
        "network": 2147483647,
        "port": 2147483647,
        "rbac_policy": 2147483647,
        "router": 2147483647,
        "subnet": 2147483647,
        "subnetpool": 2147483647,
        "firewall_policy": 2147483647,
        "firewall_rule": 2147483647,
        "health_monitor": 2147483647,
        "member": 2147483647,
        "vip": 2147483647,
        "pool": 2147483647,
        "firewall": 2147483647
    }
}
EOS
)
    curl -i -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" -X PUT -d "$data" ${NEUTRON_ENDPOINT}/quotas/${project}
done

CINDER_ENDPOINT="$(openstack endpoint list --interface public --service volumev2 -f value -c URL)"
CINDER_ENDPOINT=${CINDER_ENDPOINT%'$(tenant_id)s'}$PROJECT_ID
export CINDER_ENDPOINT
for project in $(openstack project list -f value -c ID) ; do
    data=$(cat <<-EOS
{
    "quota_set": {
        "volumes": 2147483647,
        "snapshots": 2147483647,
        "gigabytes": 2147483647,
        "backups": 2147483647,
        "backup_gigabytes": 2147483647,
        "per_volume_gigabytes": 2147483647
    }
}
EOS
)
    curl -i -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" -X PUT -d "$data" ${CINDER_ENDPOINT}/os-quota-sets/${project}
done

for project in $(openstack project list -f value -c ID) ; do
    data=$(cat <<-EOS
{
    "security_group": {
        "name": "group-for-${project}",
        "description": "Security group for ${project}",
        "tenant_id": "${project}"
    }
}
EOS
)
    curl -i -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" -X POST -d "$data" ${NEUTRON_ENDPOINT}/security-groups
done

for security_group_info in $(curl http://192.168.214.2:9696/v2.0/security-groups -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" | python -c 'import json, sys; l = json.load(sys.stdin); print "\n".join([ str("%s,%s" % (s["id"], s["tenant_id"])) for s in l["security_groups"] ])') ; do
    security_group=$(echo $security_group_info | cut -d ',' -f 1)
    tenant_id=$(echo $security_group_info | cut -d ',' -f 2)
    data=$(cat <<-EOS
{
    "security_group_rule": {
        "tenant_id": "${tenant_id}",
        "direction": "ingress",
        "protocol": "tcp",
        "ethertype": "IPv4",
        "port_range_max": "8000",
        "security_group_id": "${security_group}",
        "port_range_min": "1"
    }
}
EOS
)
    curl -i -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" -X POST -d "$data" ${NEUTRON_ENDPOINT}/security-group-rules
    security_group=$(echo $security_group_info | cut -d ',' -f 1)
    tenant_id=$(echo $security_group_info | cut -d ',' -f 2)
    data=$(cat <<-EOS
{
    "security_group_rule": {
        "tenant_id": "${tenant_id}",
        "direction": "egress",
        "protocol": "tcp",
        "ethertype": "IPv4",
        "port_range_max": "8000",
        "security_group_id": "${security_group}",
        "port_range_min": "1"
    }
}
EOS
)
    curl -i -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" -X POST -d "$data" ${NEUTRON_ENDPOINT}/security-group-rules
    security_group=$(echo $security_group_info | cut -d ',' -f 1)
    tenant_id=$(echo $security_group_info | cut -d ',' -f 2)
    data=$(cat <<-EOS
{
    "security_group_rule": {
        "tenant_id": "${tenant_id}",
        "direction": "ingress",
        "protocol": "tcp",
        "ethertype": "IPv6",
        "port_range_max": "8000",
        "security_group_id": "${security_group}",
        "port_range_min": "1"
    }
}
EOS
)
    curl -i -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" -X POST -d "$data" ${NEUTRON_ENDPOINT}/security-group-rules
    security_group=$(echo $security_group_info | cut -d ',' -f 1)
    tenant_id=$(echo $security_group_info | cut -d ',' -f 2)
    data=$(cat <<-EOS
{
    "security_group_rule": {
        "tenant_id": "${tenant_id}",
        "direction": "egress",
        "protocol": "tcp",
        "ethertype": "IPv6",
        "port_range_max": "8000",
        "security_group_id": "${security_group}",
        "port_range_min": "1"
    }
}
EOS
)
    curl -i -H "X-Auth-Token: $TOKEN" -H "Content-Type: application/json" -X POST -d "$data" ${NEUTRON_ENDPOINT}/security-group-rules
done

