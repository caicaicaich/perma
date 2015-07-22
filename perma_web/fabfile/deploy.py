from contextlib import contextmanager
from datetime import date
import os

from fabric.api import *

### HELPERS ###

@contextmanager
def web_root():
    with cd(env.REMOTE_DIR):
        if env.VIRTUALENV_NAME:
            with prefix("workon "+env.VIRTUALENV_NAME):
                yield
        else:
            yield

def run_as_web_user(*args, **kwargs):
    kwargs.setdefault('user', 'perma')
    return sudo(*args, **kwargs)

### DEPLOYMENT ###

@task(default=True)
def deploy(skip_backup=False):
    """
        Full deployment: back up database, pull code, install requirements, sync db, run migrations, collect static files, restart server.
    """
    if not skip_backup:
        backup_database()
        backup_code()
    deploy_code(restart=False)
    pip_install()
    with web_root():
        run_as_web_user("%s manage.py migrate" % env.PYTHON_BIN)
        run_as_web_user("%s manage.py collectstatic --noinput --clear" % env.PYTHON_BIN)
    restart_server()


@task
def deploy_code(restart=True, repo='origin', branch=None):
    """
        Deploy code only. This is faster than the full deploy.
    """
    with web_root():
        run_as_web_user("find . -name '*.pyc' -delete")
        if branch:
            run_as_web_user("git pull %s %s" % (repo, branch))
        else:
            run_as_web_user("git pull")
    if restart:
        restart_server()


@task
def tag_new_release(tag):
    """
        Roll develop into master and tag it
    """
    local("git checkout master")
    local("git merge develop -m 'Tagging %s. Merging develop into master'" % tag)
    local("git tag -a %s -m '%s'" % (tag, tag))
    local("git push --tags")
    local("git push")
    local("git checkout develop")


@task
def pip_install():
    with web_root():
        run_as_web_user("pip install -r requirements.txt")

@task
def restart_server():
    stop_server()
    start_server()


@task
def stop_server():
    """
        Stop the services
    """
    sudo("stop celery", shell=False)


@task
def start_server():
    """
        Start the services
    """
    sudo("start celery", shell=False)

@task
def backup_database():
    if env.DATABASE_BACKUP_DIR:
        with web_root():
            run_as_web_user("fab deploy.local_backup_database:%s" % env.DATABASE_BACKUP_DIR)

@task
def local_backup_database(backup_dir):
    # this is going to be triggered by calling fab on the remote server, so that LOCAL_DB_SETTINGS has the remote settings
    import tempfile
    from django.conf import settings

    LOCAL_DB_SETTINGS = settings.DATABASES['default']
    out_file_path = os.path.join(backup_dir, "%s.sql.gz" % date.today().isoformat())
    temp_password_file = tempfile.NamedTemporaryFile()
    temp_password_file.write("[client]\nuser=%s\npassword=%s\n" % (LOCAL_DB_SETTINGS['USER'], LOCAL_DB_SETTINGS['PASSWORD']))
    temp_password_file.flush()
    local("mysqldump --defaults-extra-file=%s -h%s %s | gzip > %s" % (
        temp_password_file.name,
        LOCAL_DB_SETTINGS['HOST'],
        LOCAL_DB_SETTINGS['NAME'],
        out_file_path
    ))

@task
def backup_code():
    if env.CODE_BACKUP_DIR:
        with web_root():
            out_file_path = os.path.join(env.CODE_BACKUP_DIR, "code_backup_%s.tar.gz" % date.today().isoformat())
            run_as_web_user("tar --xform='s:./:perma_web/:' -cvzf %s ." % out_file_path)