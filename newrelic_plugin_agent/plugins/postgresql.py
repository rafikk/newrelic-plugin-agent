"""
pgBouncer Plugin Support

"""
import psycopg2
from psycopg2 import extensions
from psycopg2 import extras

import logging
import time

from newrelic_plugin_agent.plugins import base

LOGGER = logging.getLogger(__name__)

ARCHIVE = """SELECT CAST(COUNT(*) AS INT) AS file_count,
CAST(COALESCE(SUM(CAST(archive_file ~ $r$\.ready$$r$ as INT)), 0) AS INT)
AS ready_count,CAST(COALESCE(SUM(CAST(archive_file ~ $r$\.done$$r$ AS INT)),
0) AS INT) AS done_count FROM pg_catalog.pg_ls_dir('pg_xlog/archive_status')
AS archive_files (archive_file);"""
BACKENDS = """SELECT count(*) - ( SELECT count(*) FROM pg_stat_activity WHERE
current_query = '<IDLE>' ) AS backends_active, ( SELECT count(*) FROM
pg_stat_activity WHERE current_query = '<IDLE>' ) AS backends_idle
FROM pg_stat_activity;"""
BACKENDS_9_2 = """SELECT count(*) - ( SELECT count(*) FROM pg_stat_activity WHERE
state = 'idle' ) AS backends_active, ( SELECT count(*) FROM
pg_stat_activity WHERE state = 'idle' ) AS backends_idle
FROM pg_stat_activity;"""
TABLE_SIZE_ON_DISK = """SELECT ((sum(relpages)* 8) * 1024) AS
size_relations FROM pg_class WHERE relkind IN ('r', 't');"""
TABLE_COUNT = """SELECT count(1) as relations FROM pg_class WHERE
relkind IN ('r', 't');"""
INDEX_SIZE_ON_DISK = """SELECT ((sum(relpages)* 8) * 1024) AS
size_indexes FROM pg_class WHERE relkind = 'i';"""
INDEX_COUNT = """SELECT count(1) as indexes FROM pg_class WHERE
relkind = 'i';"""
TRANSACTIONS = """SELECT sum(xact_commit) AS transactions_committed,
sum(xact_rollback) AS transactions_rollback, sum(blks_read) AS blocks_read,
sum(blks_hit) AS blocks_hit, sum(tup_returned) AS tuples_returned,
sum(tup_fetched) AS tuples_fetched, sum(tup_inserted) AS tuples_inserted,
sum(tup_updated) AS tuples_updated, sum(tup_deleted) AS tuples_deleted
FROM pg_stat_database;"""
STATIO = """SELECT sum(heap_blks_read) AS heap_blocks_read, sum(heap_blks_hit)
AS heap_blocks_hit, sum(idx_blks_read) AS index_blocks_read, sum(idx_blks_hit)
AS index_blocks_hit, sum(toast_blks_read) AS toast_blocks_read,
sum(toast_blks_hit) AS toast_blocks_hit, sum(tidx_blks_read)
AS toastindex_blocks_read, sum(tidx_blks_hit) AS toastindex_blocks_hit
FROM pg_statio_all_tables WHERE schemaname <> 'pg_catalog';"""
BGWRITER = 'SELECT * FROM pg_stat_bgwriter;'
DATABASE = 'SELECT * FROM pg_stat_database;'
LOCKS = 'SELECT mode, count(mode) AS count FROM pg_locks ' \
        'GROUP BY mode ORDER BY mode;'

LOCK_MAP = {'AccessExclusiveLock': 'Locks/Access Exclusive',
            'AccessShareLock': 'Locks/Access Share',
            'ExclusiveLock': 'Locks/Exclusive',
            'RowExclusiveLock': 'Locks/Row Exclusive',
            'RowShareLock': 'Locks/Row Share',
            'ShareUpdateExclusiveLock': 'Locks/Update Exclusive Lock',
            'ShareLock': 'Locks/Share',
            'ShareRowExclusiveLock': 'Locks/Share Row Exclusive'}


class PostgreSQL(base.Plugin):

    GUID = 'com.meetme.newrelic_postgresql_agent'

    def add_metrics(self, cursor):
        self.add_backend_metrics(cursor)
        self.add_bgwriter_metrics(cursor)
        self.add_database_metrics(cursor)
        self.add_index_metrics(cursor)
        self.add_lock_metrics(cursor)
        self.add_statio_metrics(cursor)
        self.add_table_metrics(cursor)
        self.add_transaction_metrics(cursor)
        # add_wal_metrics needs superuser to get directory listings, checks if user want's to omit that
        if self.config.get('superuser', True):
            self.add_wal_metrics(cursor)

    def add_database_metrics(self, cursor):
        cursor.execute(DATABASE)
        temp = cursor.fetchall()
        for row in temp:
            database = row['datname']
            self.add_gauge_value('Database/%s/Backends' % database, '',
                                 row.get('numbackends', 0))
            self.add_derive_value('Database/%s/Transactions/Committed' %
                                  database, '', int(row.get('xact_commit', 0)))
            self.add_derive_value('Database/%s/Transactions/Rolled Back' %
                                  database, '',
                                  int(row.get('xact_rollback', 0)))
            self.add_derive_value('Database/%s/Tuples/Read from Disk ' %
                                  database, '', int(row.get('blks_read', 0)))
            self.add_derive_value('Database/%s/Tuples/Read cache hit' %
                                  database, '',
                                  int(row.get('blks_hit', 0)))
            self.add_derive_value('Database/%s/Tuples/Returned/From Sequential '
                                  'Scan' % database, '',
                                  int(row.get('tup_returned', 0)))
            self.add_derive_value('Database/%s/Tuples/Returned/From Bitmap '
                                  'Scan' % database, '',
                                  int(row.get('tup_fetched', 0)))
            self.add_derive_value('Database/%s/Tuples/Writes/Inserts' %
                                  database, '',
                                  int(row.get('tup_inserted', 0)))
            self.add_derive_value('Database/%s/Tuples/Writes/Updates' %
                                  database, '',
                                  int(row.get('tup_updated', 0)))
            self.add_derive_value('Database/%s/Tuples/Writes/Deletes' %
                                  database, '',
                                  int(row.get('tup_deleted', 0)))
            self.add_derive_value('Database/%s/Conflicts' %
                                  database, '',
                                  int(row.get('conflicts', 0)))

    def add_backend_metrics(self, cursor):
        if self._get_server_version(cursor.connection) < (9, 2, 0):
            cursor.execute(BACKENDS)
        else:
            cursor.execute(BACKENDS_9_2)
        temp = cursor.fetchone()
        self.add_gauge_value('Backends/Active', '',
                             temp.get('backends_active', 0))
        self.add_gauge_value('Backends/Idle', '',
                             temp.get('backends_idle', 0))

    def add_bgwriter_metrics(self, cursor):
        cursor.execute(BGWRITER)
        temp = cursor.fetchone()
        self.add_derive_value('Background Writer/Checkpoints/Scheduled',
                              '',
                              temp.get('checkpoints_timed', 0))
        self.add_derive_value('Background Writer/Checkpoints/Requested',
                              '',
                              temp.get('checkpoints_requests', 0))

    def add_index_metrics(self, cursor):
        cursor.execute(INDEX_COUNT)
        temp = cursor.fetchone()
        self.add_gauge_value('Objects/Indexes', '',
                             temp.get('indexes', 0))
        cursor.execute(INDEX_SIZE_ON_DISK)
        temp = cursor.fetchone()
        self.add_gauge_value('Disk Utilization/Indexes', 'bytes',
                             temp.get('size_indexes', 0))

    def add_lock_metrics(self, cursor):
        cursor.execute(LOCKS)
        temp = cursor.fetchall()
        for lock in LOCK_MAP:
            found = False
            for row in temp:
                if row['mode'] == lock:
                    found = True
                    self.add_gauge_value(LOCK_MAP[lock], '', int(row['count']))
            if not found:
                    self.add_gauge_value(LOCK_MAP[lock], '', 0)

    def add_statio_metrics(self, cursor):
        cursor.execute(STATIO)
        temp = cursor.fetchone()
        self.add_derive_value('IO Operations/Heap/Reads', '',
                              int(temp.get('heap_blocks_read', 0)))
        self.add_derive_value('IO Operations/Heap/Hits', '',
                              int(temp.get('heap_blocks_hit', 0)))
        self.add_derive_value('IO Operations/Index/Reads', '',
                              int(temp.get('index_blocks_read', 0)))
        self.add_derive_value('IO Operations/Index/Hits', '',
                              int(temp.get('index_blocks_hit', 0)))
        self.add_derive_value('IO Operations/Toast/Reads', '',
                              int(temp.get('toast_blocks_read', 0)))
        self.add_derive_value('IO Operations/Toast/Hits', '',
                              int(temp.get('toast_blocks_hit', 0)))
        self.add_derive_value('IO Operations/Toast Index/Reads', '',
                              int(temp.get('toastindex_blocks_read', 0)))
        self.add_derive_value('IO Operations/Toast Index/Hits', '',
                              int(temp.get('toastindex_blocks_hit', 0)))

    def add_table_metrics(self, cursor):
        cursor.execute(TABLE_COUNT)
        temp = cursor.fetchone()
        self.add_gauge_value('Objects/Tables', '',
                             temp.get('relations', 0))
        cursor.execute(TABLE_SIZE_ON_DISK)
        temp = cursor.fetchone()
        self.add_gauge_value('Disk Utilization/Tables', 'bytes',
                             temp.get('size_relations', 0))

    def add_transaction_metrics(self, cursor):
        cursor.execute(TRANSACTIONS)
        temp = cursor.fetchone()
        self.add_derive_value('Transactions/Committed', '',
                              int(temp.get('transactions_committed', 0)))
        self.add_derive_value('Transactions/Rolled Back', '',
                              int(temp.get('transactions_rollback', 0)))

        self.add_derive_value('Tuples/Read from Disk', '',
                              int(temp.get('blocks_read', 0)))
        self.add_derive_value('Tuples/Read cache hit', '',
                              int(temp.get('blocks_hit', 0)))

        self.add_derive_value('Tuples/Returned/From Sequential Scan',
                              '',
                              int(temp.get('tuples_returned', 0)))
        self.add_derive_value('Tuples/Returned/From Bitmap Scan',
                              '',
                              int(temp.get('tuples_fetched', 0)))

        self.add_derive_value('Tuples/Writes/Inserts', '',
                              int(temp.get('tuples_inserted', 0)))
        self.add_derive_value('Tuples/Writes/Updates', '',
                              int(temp.get('tuples_updated', 0)))
        self.add_derive_value('Tuples/Writes/Deletes', '',
                              int(temp.get('tuples_deleted', 0)))

    def add_wal_metrics(self, cursor):
        cursor.execute(ARCHIVE)
        temp = cursor.fetchone()
        self.add_derive_value('Archive Status/Total', '',
                              temp.get('file_count', 0))
        self.add_gauge_value('Archive Status/Ready', '',
                             temp.get('ready_count', 0))
        self.add_derive_value('Archive Status/Done', '',
                              temp.get('done_count', 0))

    @property
    def dsn(self):
        """Create a DSN to connect to

        :return str: The DSN to connect

        """
        dsn = "host='%(host)s' port=%(port)i dbname='%(dbname)s' " \
              "user='%(user)s'" % self.config
        if self.config.get('password'):
            dsn += " password='%s'" % self.config['password']
        return dsn

    def connect(self):
        conn = psycopg2.connect(self.dsn)
        conn.set_isolation_level(extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        return conn

    def poll(self):
        LOGGER.info('Polling PostgreSQL at %(host)s:%(port)s', self.config)
        start_time = time.time()
        self.derive = dict()
        self.gauge = dict()
        self.rate = dict()

        conn = self.connect()
        cursor = conn.cursor(cursor_factory=extras.DictCursor)
        self.add_metrics(cursor)
        cursor.close()
        conn.close()

        LOGGER.info('Polling complete in %.2f seconds',
                    time.time() - start_time)

    def _get_server_version(self, connection):
        """Get connection server version in PEP 369 format"""
        v = connection.server_version
        return (v % 1000000 / 10000, v % 10000 / 100, v % 100)

