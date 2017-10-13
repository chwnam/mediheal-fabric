import os
from fabric.api import cd, get, local, put, run
from fabric.contrib.files import exists


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
        run('rm -rf {0}/*'.format(env.target_wp_path))

    if not exists(env.target_wp_path):
        run('mkdir {}'.format(env.target_wp_path))

    with cd(env.target_wp_path):
        run('tar xzf {} -C {} --strip=1'.format(env.target_wp_snapshot, env.target_wp_path))
        run('find . -type f -exec chmod 664 {} \;')
        run('find . -type d -exec chmod 775 {} \;')
        if exists(wp_config_moved):
            run('rm -f ./wp-config.php')
            run('mv {} ./wp-config.php'.format(wp_config_moved))

    fixed_params = [env.target_wp_cli, env.target_wp_path, env.target_wp_url]
    search_replaces = [
        [env.origin_wp_path, env.target_wp_path, 'wp_posts wp_postmeta wp_options'],
        [env.origin_wp_url, env.target_wp_url, 'wp_posts wp_postmeta wp_options'],
    ]

    for search_replace in search_replaces:
        run('{} --path={} --url={} search-replace {} {} {}'.format(*(fixed_params + search_replace)))

    # clean up
    run('rm -f {} {}'.format(env.target_sql_snapshot, env.target_wp_snapshot))
    local('rm -f {} {}'.format(env.local_sql_snapshot, env.local_wp_snapshot))

    with cd(os.path.join(env.target_wp_path, 'wp-content/mu-plugins/ivy-mu')):
        run('composer dump-autoload --optimize')

    with cd(os.path.join(env.target_wp_path, 'wp-content/plugins/mediheal-custom')):
        run('composer dump-autoload --optimize')

    run('fix-ownership')


def dump_old_member(env):
    run('mysql -u{} -p{} {} -e "SELECT * FROM {}" | sed \'s/\t/","/g;s/^/"/;s/$/"/;\' > table.csv'.format(
        env.db_user,
        env.db_pass,
        env.db_name,
        env.db_table,
        env.db_csv
    ))
    get(env.db_csv, env.local_csv)
