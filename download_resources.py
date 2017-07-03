#!/usr/bin/env python

import argparse
import csv
import ConfigParser
import os
import tarfile

import psycopg2

def write_csv(filename, columns, rows, append=False):
    if append:
        mode = 'a'
    else:
        mode = 'w'
    with open(filename, mode) as f:
        csv_writer = csv.writer(f)
        if not append:
            csv_writer.writerow(columns)
        csv_writer.writerows(rows)

def get_pg_connection(service):
    conf = ConfigParser.ConfigParser()
    conf.read('/etc/%s/%s.conf' % (service, service))
    pg_connection = conf.get('database', 'connection')
    return pg_connection

def run_select(pg_connection, query):
    connection = psycopg2.connect(pg_connection)
    cursor = connection.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()
    columns = [column.name for column in cursor.description]
    return columns, rows

def download_keypairs(workspace):
    print("Dumping keypairs from database")
    pg_connection = get_pg_connection('nova')
    query = "SELECT id, name, user_id, public_key, type FROM key_pairs WHERE deleted = 0"
    keypair_columns, keypair_rows = run_select(pg_connection, query)
    csvfile = workspace + '/saved_nova_keypairs.csv'
    print("Writing keypairs to %s" % csvfile)
    write_csv(csvfile, keypair_columns, keypair_rows)

def download_quotas(service, query, workspace, append=False):
    print("Dumping quotas from %s database" % service)
    pg_connection = get_pg_connection(service)
    quota_columns, quota_rows = run_select(pg_connection, query)
    csvfile = "%s/saved_%s_quotas.csv" % (workspace, service)
    print("Writing %s quotas to %s" % (service, csvfile))
    write_csv(csvfile, quota_columns, quota_rows, append=append)

def download_nova_quotas(workspace):
    query = "SELECT '' as user_id, project_id, resource, hard_limit FROM quotas WHERE deleted = 0;"
    download_quotas('nova', query, workspace)
    query = "SELECT user_id, project_id, resource, hard_limit FROM project_user_quotas WHERE deleted = 0;"
    download_quotas('nova', query, workspace, append=True)

def download_neutron_quotas(workspace):
    query = 'SELECT tenant_id, resource, "limit" FROM quotas;'
    download_quotas('neutron', query,  workspace)

def download_cinder_quotas(workspace):
    query = "SELECT project_id, resource, hard_limit FROM quotas WHERE deleted = false;"
    download_quotas('cinder', query, workspace)

def download_security_groups(workspace):
    print("Dumping security groups from database")
    pg_connection = get_pg_connection('neutron')
    query = "SELECT sg.id, " \
            "sg.name, " \
            "sg.description, " \
            "sgr.tenant_id, " \
            "sgr.remote_group_id, " \
            "sgr.direction, " \
            "sgr.ethertype, " \
            "sgr.protocol, " \
            "sgr.port_range_min, " \
            "sgr.port_range_max, " \
            "sgr.remote_ip_prefix " \
            "FROM securitygroups AS sg " \
            "JOIN securitygrouprules AS sgr " \
            "ON sg.id = sgr.security_group_id"
    security_group_columns, security_group_rows = run_select(pg_connection, query)
    csvfile = workspace + '/saved_neutron_security_groups.csv'
    print("Writing security groups to %s" % csvfile)
    write_csv(csvfile, security_group_columns, security_group_rows)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', required=True,
                        help='Workspace directory where data will be stored. '
                             'Ensure this space is large enough for your '
                             'keypair, quota, and security group data.')
    parser.add_argument('--keypairs', action='store_true',
                        help='Download keypairs only.')
    parser.add_argument('--quotas', action='store_true',
                        help='Download quotas only.')
    parser.add_argument('--nova-quotas', action='store_true',
                        help='Download nova quotas only.')
    parser.add_argument('--neutron-quotas', action='store_true',
                        help='Download neutron quotas only.')
    parser.add_argument('--cinder-quotas', action='store_true',
                        help='Download cinder quotas only.')
    parser.add_argument('--security-groups', action='store_true',
                        help='Download security groups only.')
    args = parser.parse_args()
    workspace = args.directory
    if not os.path.exists(workspace):
        os.makedirs(workspace)

    run_all = False
    if not any([args.keypairs, args.quotas, args.nova_quotas,
                args.neutron_quotas, args.cinder_quotas, args.security_groups]):
        run_all = True
    if run_all or args.keypairs:
        download_keypairs(workspace)
    if run_all or args.quotas:
        download_nova_quotas(workspace)
        download_neutron_quotas(workspace)
        download_cinder_quotas(workspace)
    if run_all or args.security_groups:
        download_security_groups(workspace)
    tarball_path = workspace + '.tar.bz2'
    with tarfile.open(tarball_path, mode='w:bz2') as tarball:
        tarball.add(workspace)
        tarball.close()
    print("Tarball stored at %s" % tarball_path)

if __name__ == '__main__':
    main()
