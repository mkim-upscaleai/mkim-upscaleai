"""
DUT-side CONFIG_DB command prefixes without hardcoding redis DB index 4.

Helpers return prefixes for ``redis-cli -n <id>`` (and ``docker exec ...`` and
argv variants) where ``id`` is read from
``/var/run/redis/sonic-db/database_config.json`` (CONFIG_DB session / layout safe).
Falls back to ``id=4`` with a warning if the file or key is missing.

We intentionally do NOT default to ``sonic-db-cli`` even when it's present,
because sonic-db-cli normalises some command outputs differently from
redis-cli (e.g. ``HEXISTS``/``EXISTS`` return ``True``/``False`` strings
instead of ``1``/``0``). Sticking to redis-cli keeps the migration
semantically transparent — code that worked with the pre-migration
``redis-cli -n 4 …`` literal still works.

Non-CONFIG databases should keep using explicit DB names or numeric indices elsewhere.
"""
from __future__ import absolute_import, division, print_function

import json
import logging

logger = logging.getLogger(__name__)


def get_config_db_redis_id(duthost, config_path="/var/run/redis/sonic-db/database_config.json"):
    """
    Return the Redis logical DB index for CONFIG_DB from the DUT's database_config.json.

    Falls back to 4 if the file or key is missing (legacy default).
    """
    try:
        rc = duthost.shell("cat {}".format(config_path), module_ignore_errors=True)
        if rc.get("rc") != 0:
            raise RuntimeError("cat failed rc={}".format(rc.get("rc")))
        data = json.loads(rc["stdout"])
        db_entry = data.get("DATABASES", {}).get("CONFIG_DB")
        if not db_entry or "id" not in db_entry:
            raise KeyError("CONFIG_DB id not in database_config")
        return int(db_entry["id"])
    except Exception as err:
        logger.warning("get_config_db_redis_id: using default 4 (%s)", err)
        return 4


def sonic_db_cli_available(duthost):
    chk = duthost.shell(
        "test -x /usr/local/bin/sonic-db-cli -o -x /usr/bin/sonic-db-cli",
        module_ignore_errors=True,
    )
    return chk.get("rc") == 0


def config_db_shell_prefix(duthost, namespace=None):
    """
    Shell command prefix for CONFIG_DB access, including trailing space.

    Returns a ``redis-cli -n <id>`` prefix with the CONFIG_DB index resolved
    dynamically from ``database_config.json`` (so multi-DB / non-default layouts
    work). We intentionally do NOT use ``sonic-db-cli`` even when available,
    because it normalises some command outputs (e.g. ``HEXISTS`` returns
    ``True``/``False`` instead of ``1``/``0``); preserving raw redis-cli
    semantics matches what pre-migration code expects.

    For callers that explicitly want the ``sonic-db-cli`` flavour (e.g. for its
    multi-namespace handling), call ``sonic_db_cli_available`` and build the
    command manually.

    Args:
        duthost: Ansible SonicHost for the DUT.
        namespace: Optional namespace; currently a no-op for the redis-cli
            path. Callers needing multi-ASIC routing should use netns-aware
            execution (e.g. via ``dut_asic`` / ``run_redis_cmd``).

    Returns:
        str: e.g. ``redis-cli -n 4 `` (with trailing space).
    """
    db_id = get_config_db_redis_id(duthost)
    return "redis-cli -n {db_id} ".format(db_id=db_id)


def config_db_redis_cli_prefix(duthost):
    """
    ``redis-cli -n <CONFIG_DB id> `` including trailing space.

    Use for shell snippets that need raw redis-cli behavior (for example ``--scan``
    in a ``for`` loop) while still resolving the CONFIG DB index from
    ``database_config.json``.
    """
    db_id = get_config_db_redis_id(duthost)
    return "redis-cli -n {db_id} ".format(db_id=db_id)


def config_db_redis_cli_argv(duthost):
    """
    Return an argv-style prefix list ``["redis-cli", "-n", "<id>"]`` for callers
    that build redis-cli invocations as Python lists (e.g. ``run_redis_cmd(argv=[...])``).

    Use:
        argv = config_db_redis_cli_argv(duthost) + ["HGET", key, field]
        result = dut_asic.run_redis_cmd(argv=argv)
    """
    db_id = get_config_db_redis_id(duthost)
    return ["redis-cli", "-n", str(db_id)]


def config_db_database_container_redis_prefix(duthost, redis_cluster=False):
    """
    Prefix for ``docker exec -i database redis-cli ...`` style commands (trailing space).

    Used where tests talk to the database container's Redis directly. Resolves CONFIG_DB
    index from database_config.json instead of hardcoding ``-n 4``.

    Args:
        duthost: SonicHost.
        redis_cluster: Pass True to insert ``-c`` after the ``-n`` (cluster mode).
    """
    db_id = get_config_db_redis_id(duthost)
    cluster = " -c" if redis_cluster else ""
    return "docker exec -i database redis-cli -n {id}{cluster} ".format(
        id=db_id, cluster=cluster
    )
