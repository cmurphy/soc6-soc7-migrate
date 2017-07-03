SOC6 -> SOC7 Data Transfer
==========================

Download keypairs, quotas, and security groups from a SOC6 installation and
upload them safely to a SOC7 installation.

Prerequisites
-------------

This migration is designed to accomodate LDAP users that have been migrated
from the old keystone hybrid backend to the new domain-specific configuration
model, mapping resources tied to user IDs to the correct newly generated ID.
However, it assumes that project IDs have remained constant.

Usage
-----

### Download

On a SOC6 controller, run the download\_resources.py script:

```
# ./download_resources.py --directory /path/to/data/directory
```

This uses the postgresql credentials stored in the nova, neutron, and cinder
configuration files to directly access the database, dump selected values from
it into CSV files, and create a bzip2'd tarball.

You can selectively download only certain resources with the following options:

* ``--keypairs`` download nova keypairs only
* ``--quotas`` download quotas only
* ``--nova-quotas`` download quotas for nova only
* ``--neutron-quotas`` download quotas for neutron only
* ``--cinder-quotas`` download quotas for cinder only
* ``--security-groups`` download neutron security groups only

This download should be reasonably fast since it is merely querying the
local database.

### Upload

**IMPORTANT:** Please take a database backup from your SOC7 controller before
proceeding.

Copy the tarball created on the SOC6 controller onto the SOC7 controller.

On the SOC7 controller, run the upload\_resources.py script:

```
# source .openrc
# ./upload_resources.py --tarball /path/to/soc6/tarball
```

This uses the OpenStack APIs to upload the resources stored in the tarball,
rather than inserting them directly into the database. The reason we do it this
way is that we want to preserve existing data already created in the SOC7 cloud,
as well as avoid complications due to changed database schemas between releases.
For high volumes of data, this upload may take a long time.

Like with the download option, you can selectively upload only certain resources
with the following options:

* ``--keypairs`` upload nova keypairs only
* ``--quotas`` upload quotas only
* ``--nova-quotas`` upload quotas for nova only
* ``--neutron-quotas`` upload quotas for neutron only
* ``--cinder-quotas`` upload quotas for cinder only
* ``--security-groups`` upload neutron security groups only

Keypairs and quotas are idempotent, but security groups are not, as it is
possible to upload multiple security groups with the same name for the same
project. In order to avoid altering existing SOC7 security groups that may have
been created before the migration, as well as to avoid conflicts that could
arise by trying to re-run this migration, the upload script tracks security
groups it has uploaded so far and writes these groups to a local file in the
uncompressed data directory. If the security group upload is unsuccessful, it
will read this file to remember its progress.
