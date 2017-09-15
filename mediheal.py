import os
import re
from tempfile import NamedTemporaryFile

from fabric.api import cd, get, run, put
from fabric.contrib.files import exists


class TemporaryFile(object):
    def __init__(self):
        self.f = NamedTemporaryFile('w', delete=False)

    def __del__(self):
        if self.f and self.f.name:
            os.remove(self.f.name)

    def write(self, content):
        self.f.write(content)

    def close(self):
        self.f.close()

    @property
    def name(self):
        return self.f.name


def origin2local(env):
    # MariaDB DUMP
    if not exists(os.path.dirname(env.origin_sql_snapshot)):
        run('mkdir {}'.format(os.path.dirname(env.origin_sql_snapshot)))

    run(
        'mysqldump --add-drop-table --user={} --password={} {} 2>/dev/null | gzip > {}'.format(
            env.origin_db_user,
            env.origin_db_pass,
            env.origin_db_name,
            env.origin_sql_snapshot
        )
    )

    # WP DUMP
    if not exists(os.path.dirname(env.origin_wp_snapshot)):
        run('mkdir {}'.format(os.path.dirname(env.origin_wp_snapshot)))

    with cd(os.path.dirname(env.origin_wp_path)):
        run('tar czf {} {}'.format(env.origin_wp_snapshot, os.path.basename(env.origin_wp_path)))

    get(env.origin_sql_snapshot, env.local_sql_snapshot)
    get(env.origin_wp_snapshot, env.local_wp_snapshot)

    run('rm -f {} {}'.format(env.origin_wp_snapshot, env.origin_sql_snapshot))


def local2target(env):
    put(env.local_sql_snapshot, env.target_sql_snapshot)
    put(env.local_wp_snapshot, env.target_wp_snapshot)

    run(
        'gunzip -c {} | {} | mysql --user={} --password={} {} 2>/dev/null'.format(
            env.target_sql_snapshot,
            "sed -e 's/ENGINE=Aria/ENGINE=InnoDB/' -e 's/PAGE_CHECKSUM=1//' -e 's/TRANSACTIONAL=1//'",
            env.target_db_user,
            env.target_db_pass,
            env.target_db_name
        )
    )

    wp_config = os.path.join(env.target_wp_path, 'wp-config.php')
    wp_config_moved = os.path.join(os.path.dirname(env.target_wp_path), 'wp-config.php')

    if exists(wp_config):
        run('mv {} {}'.format(wp_config, wp_config_moved))

    if exists(env.target_wp_path):
        run('rm -rf {}'.format(env.target_wp_path))

    if not exists(env.target_wp_path):
        run('mkdir {}'.format(env.target_wp_path))

    with cd(env.target_wp_path):
        run('tar xzf {} -C {} --strip=1'.format(env.target_wp_snapshot, env.target_wp_path))
        run('find . -type f -exec chmod 664 {} \;')
        run('find . -type d -exec chmod 775 {} \;')
        if exists(wp_config_moved):
            run('rm -f ./wp-config.php')
            run('mv {} ./wp-config.php'.format(wp_config_moved))

    replace_items = [
        {
            'table': 'wp_options',
            'field': 'option_value',
        },
        {
            'table': 'wp_posts',
            'field': 'post_content',
        },
        {
            'table': 'wp_posts',
            'field': 'guid',
        },
        {
            'table': 'wp_postmeta',
            'field': 'meta_value',
        },
        {
            'table': 'wp_usermeta',
            'field': 'meta_value',
        },
    ]

    for item in replace_items:
        run(
            'mysql -u{} -p{} {} -e "UPDATE {} SET {} = REPLACE({}, \'{}\', \'{}\')"'.format(
                env.target_db_user,
                env.target_db_pass,
                env.target_db_name,
                item['table'],
                item['field'],
                item['field'],
                env.origin_wp_url,
                env.target_wp_url,
            )
        )

    run(
        'mysql -u{} -p{} {} -e "UPDATE {} SET {} = REPLACE({}, \'{}\', \'{}\')"'.format(
            env.target_db_user,
            env.target_db_pass,
            env.target_db_name,
            'wp_options',
            'option_value',
            'option_value',
            '/home/apple.wpkorea.org/public_html/wp-content/',
            '/home/mediheal/public_html/wp-content/',
        )
    )

    update_serialized_option_value(env, 'wp_options', 'botdetect_options', env.target_wp_url + '.+?')
    update_serialized_option_value(env, 'wp_options', 'botdetect_options', '/home/mediheal/public_html/wp-content/.+?')

    run('rm -f {} {}'.format(env.target_sql_snapshot, env.target_wp_snapshot))


def update_serialized_option_value(env, option_table, option_name, expr):

    def replace_matched(match):
        return 's:%d:\"%s\";' % (len(match.group(2)), match.group(2))

    m = run(
        'mysql -u{} -p{} {} -sN -r -e {} 2>&1 | grep -v "Warning:"'.format(
            env.target_db_user,
            env.target_db_pass,
            env.target_db_name,
            '"SELECT option_value AS \'\' FROM %s WHERE option_name=\'%s\'"' % (option_table, option_name)
        )
    )

    expr = 's:(\d+):"(%s)";' % expr
    replaced = re.sub(expr, replace_matched, m)

    f = TemporaryFile()
    query = 'UPDATE %s SET option_value=\'%s\' WHERE option_name=\'%s\';' % (option_table, replaced, option_name)
    f.write(query)
    f.close()
    remote_file = '/home/mediheal/' + os.path.basename(f.name)
    put(f.name, remote_file)

    run(
        'mysql -u{} -p{} {} < {}'.format(
            env.target_db_user,
            env.target_db_pass,
            env.target_db_name,
            remote_file
        )
    )
    run('rm -f {}'.format(remote_file))
