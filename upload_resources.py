#!/usr/bin/env python

import argparse
import atexit
import csv
import ConfigParser
import os
import sys
import tarfile

from cinderclient import client as cinder_client
from keystoneclient.v3 import client as keystone_client
from neutronclient.v2_0 import client as neutron_client
from neutronclient.common import exceptions as neutron_exceptions
from novaclient import client as nova_client
from novaclient import exceptions as nova_exceptions
import os_client_config
import psycopg2

def get_session(service):
  try:
    return os_client_config.make_rest_client(service)
  except os_client_config.exceptions.OpenStackConfigException:
    print("Source your .openrc file before running this script.")
    sys.exit(1)

def show_progress(total):
    progress = 1
    for item in range(1, total + 1):
        sys.stdout.write('\r')
        sys.stdout.write('%d/%d' % (progress, total))
        sys.stdout.flush()
        progress += 1
        yield

def upload_keypairs(workspace):
    # Populate the id_mapping table
    session = get_session('identity')
    keystone = keystone_client.Client(session=session)
    print("Populating the id_mapping table with LDAP users. "
          "This may take some time.")
    for domain in keystone.domains.list():
        keystone.users.list(domain=domain.id)
    print("Completed id_mapping table population.")

    # Collect the old user IDs
    keystone_conf = ConfigParser.ConfigParser()
    keystone_conf.read('/etc/keystone/keystone.conf.d/100-keystone.conf')
    pg_connection = keystone_conf.get('database', 'connection')
    connection = psycopg2.connect(pg_connection)
    cursor = connection.cursor()
    cursor.execute('SELECT local_id, public_id FROM id_mapping;')
    id_map = dict(cursor.fetchall())

    # Upload keypairs
    session = get_session('compute')
    nova = nova_client.Client('2.34', session=session)
    print("Uploading keypairs.")
    with open(workspace + '/saved_nova_keypairs.csv') as f:
        saved_nova_keypairs = list(csv.DictReader(f))
        found_conflict = False
        keypairs_progress = show_progress(len(saved_nova_keypairs))
        for kp in saved_nova_keypairs:
            if kp['user_id'] in id_map:
                user_id = id_map[kp['user_id']]
            else:
                user_id = kp['user_id']
            try:
                nova.keypairs.create(name=kp['name'],
                                     user_id=user_id,
                                     public_key=kp['public_key'],
                                     key_type=kp['type'])
            except nova_exceptions.Conflict:
                found_conflict = True
                logfile = 'nova_unimported_keypairs.log'
                with open(logfile, 'a') as log:
                    log.write("Failed to import keypair: name %(name)s, "
                              "user_id %(user_id)s, public_key %(public_key)s, "
                              "type: %(type)s\n" % {'name': kp['name'],
                                                 'user_id': user_id,
                                                 'public_key': kp['public_key'],
                                                 'type': kp['type'] })
            keypairs_progress.next()
        if found_conflict:
            print("Attempted to store some keypairs for users that already "
                  "have a keypair with that name. Unimported keypairs have "
                  "been logged to %(logfile)s" % {'logfile': logfile})
        print("\n")

def upload_nova_quotas(workspace):
    session = get_session('compute')
    nova = nova_client.Client('2.34', session=session)
    # Collect the old user IDs for user-specific quotas
    keystone_conf = ConfigParser.ConfigParser()
    keystone_conf.read('/etc/keystone/keystone.conf.d/100-keystone.conf')
    pg_connection = keystone_conf.get('database', 'connection')
    connection = psycopg2.connect(pg_connection)
    cursor = connection.cursor()
    cursor.execute('SELECT local_id, public_id FROM id_mapping;')
    id_map = dict(cursor.fetchall())
    print("Uploading nova quotas.")
    with open(workspace + '/saved_nova_quotas.csv') as f:
        saved_nova_quotas = csv.DictReader(f)
        quotas_dict = {}
        project_user_quotas_dict = {}
        for quota in saved_nova_quotas:
            project_id = quota['project_id']
            if not quotas_dict.get(project_id):
                quotas_dict[project_id] = {}
            if quota.get('user_id'):
                if quota['user_id'] in id_map:
                    user_id = id_map[quota['user_id']]
                else:
                    user_id = quota['user_id']
                if not quotas_dict[project_id].get(user_id):
                    quotas_dict[project_id][user_id] = {'user_id': user_id}
                quotas_dict[project_id][user_id][quota['resource']] = quota['hard_limit']
            else:
                if not quotas_dict[project_id].get('project_level_quotas'):
                    quotas_dict[project_id]['project_level_quotas'] = {}
                quotas_dict[project_id]['project_level_quotas'][quota['resource']] = quota['hard_limit']
        quotas_progress = show_progress(len(quotas_dict))
        for project_id, quotas in quotas_dict.iteritems():
            project_level_quotas = quotas.pop('project_level_quotas')
            nova.quotas.update(project_id, **project_level_quotas)
            for _, kwargs in quotas.iteritems():
                nova.quotas.update(project_id, **kwargs)
            quotas_progress.next()
        print("\n")

def upload_neutron_quotas(workspace):
    session = get_session('network')
    neutron = neutron_client.Client(session=session)
    print("Uploading neutron quotas.")
    with open(workspace + '/saved_neutron_quotas.csv') as f:
        saved_neutron_quotas = csv.DictReader(f)
        quotas_dict = {}
        for quota in saved_neutron_quotas:
            if quota['resource'] in ['health_monitor', 'vip', 'member']:
                continue
            project_id = quota['tenant_id']
            if not quotas_dict.get(project_id):
                quotas_dict[project_id] = {}
            quotas_dict[project_id][quota['resource']] = quota['limit']
        quotas_progress = show_progress(len(quotas_dict))
        for project_id, kwargs in quotas_dict.iteritems():
            neutron.update_quota(project_id, {'quota': kwargs})
            quotas_progress.next()
        print("\n")


def upload_cinder_quotas(workspace):
    session = get_session('volume')
    cinder = cinder_client.Client('2', session=session)
    print("Uploading cinder quotas.")
    with open(workspace + '/saved_cinder_quotas.csv') as f:
        saved_quotas = csv.DictReader(f)
        quotas_dict = {}
        for quota in saved_quotas:
            project_id = quota['project_id']
            if not quotas_dict.get(project_id):
                quotas_dict[project_id] = {}
            quotas_dict[project_id][quota['resource']] = quota['hard_limit']
        quotas_progress = show_progress(len(quotas_dict))
        for project_id, kwargs in quotas_dict.iteritems():
            cinder.quotas.update(project_id, **kwargs)
            quotas_progress.next()
        print("\n")

def upload_security_groups(workspace):
    session = get_session('network')
    neutron = neutron_client.Client(session=session)
    with open(workspace + '/saved_neutron_security_groups.csv') as f:
        saved_security_groups = csv.DictReader(f)
        security_groups_dict = {}
        for security_group_rule in saved_security_groups:
            security_group_id = security_group_rule['id']
            if not security_groups_dict.get(security_group_id):
                security_groups_dict[security_group_id] = {
                    'name': security_group_rule['name'],
                    'description': security_group_rule['description'] or None,
                    'project_id': security_group_rule['tenant_id'],
                    'rules': []
                }
            security_groups_dict[security_group_id]['rules'].append({
                'project_id': security_group_rule['tenant_id'],
                'remote_group_id': security_group_rule['remote_group_id'] or None,
                'direction': security_group_rule['direction'] or None,
                'ethertype': security_group_rule['ethertype'] or None,
                'protocol': security_group_rule['protocol'] or None,
                'port_range_min': security_group_rule['port_range_min'] or None,
                'port_range_max': security_group_rule['port_range_max'] or None,
                'remote_ip_prefix': security_group_rule['remote_ip_prefix'] or None
            })

    sg_id_map = {}

    crashfile = workspace + '/security_groups_crash.txt'
    def save_state():
        with open(crashfile, 'w') as f:
            print("Saving security groups uploaded so far, do not interrupt.")
            csv_writer = csv.writer(f)
            csv_writer.writerows(sg_id_map.items())
    crashed = True
    def crash_callback():
        if crashed:
            save_state()
    atexit.register(crash_callback)

    print("Uploading security groups.")
    if os.path.isfile(crashfile):
        with open(crashfile) as f:
            sg_id_map = dict(csv.reader(f))
    security_groups_progress = show_progress(len(security_groups_dict))
    for sg_id, sg in security_groups_dict.iteritems():
        security_group = {
            'security_group': {
                'name': sg['name'],
                'project_id': sg['project_id']
            }
        }
        # Creates default security group if it doesn't exist
        security_group['security_group']['description'] = sg['description']
        try:
            # Except for the default group, this will always create a new security
            # group even if one already exists by the given name for that project
            new_sg = neutron.create_security_group(security_group)['security_group']
        except neutron_exceptions.Conflict:
            # There is only one default security group. Trying to recreate the
            # default group is the only thing that will trip this exception.
            name = security_group['security_group']['name']
            project_id = security_group['security_group']['project_id']
            new_sg = neutron.find_resource('security_group', name, project_id=project_id)
        security_groups_progress.next()
        sg_id_map[sg_id] = new_sg['id']
    crashed = False
    save_state()

    print("\nUploading security group rules.")
    security_groups_progress = show_progress(len(sum([security_group['rules'] for security_group in security_groups_dict.values()], [])))
    for sg_id, sg in security_groups_dict.iteritems():
        for rule in sg['rules']:
            security_group_rule = rule.copy()
            security_group_rule['security_group_id'] = sg_id_map[sg_id]
            security_group_rule['remote_group_id'] = sg_id_map.get(rule['remote_group_id'])
            security_group_rule = {
                'security_group_rule': dict((k,v) for k,v in security_group_rule.iteritems() if v)
            }
            try:
                neutron.create_security_group_rule(security_group_rule)
            except neutron_exceptions.Conflict:
                # Conflicts only happen if the rule is identical, so no need to worry about it.
                pass
            security_groups_progress.next()
    print("\n")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tarball', required=True, help='Tarball to extract from')
    parser.add_argument('--keypairs', action='store_true',
                        help='Upload keypairs only.')
    parser.add_argument('--quotas', action='store_true',
                        help='Upload all quotas only.')
    parser.add_argument('--nova-quotas', action='store_true',
                        help='Upload nova quotas only.')
    parser.add_argument('--neutron-quotas', action='store_true',
                        help='Upload neutron quotas only.')
    parser.add_argument('--cinder-quotas', action='store_true',
                        help='Upload cinder quotas only.')
    parser.add_argument('--security-groups', action='store_true',
                        help='Upload security groups only.')
    args = parser.parse_args()
    run_all = False
    if not any([args.keypairs, args.quotas, args.nova_quotas,
                args.neutron_quotas, args.cinder_quotas, args.security_groups]):
        run_all = True
    with tarfile.open(args.tarball, 'r:bz2') as tarball:
        workspace = tarball.getnames()[0]
        tarball.extractall()
    if run_all or args.keypairs:
        upload_keypairs(workspace)
    if run_all or args.quotas or args.nova_quotas:
        upload_nova_quotas(workspace)
    if run_all or args.quotas or args.neutron_quotas:
        upload_neutron_quotas(workspace)
    if run_all or args.quotas or args.cinder_quotas:
        upload_cinder_quotas(workspace)
    if run_all or args.security_groups:
        upload_security_groups(workspace)

if __name__ == '__main__':
    main()
