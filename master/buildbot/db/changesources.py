# This file is part of Buildbot.  Buildbot is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright Buildbot Team Members


import sqlalchemy as sa

from twisted.internet import defer

from buildbot.db import NULL
from buildbot.db import base


class ChangeSourceAlreadyClaimedError(Exception):
    pass


class ChangeSourcesConnectorComponent(base.DBConnectorComponent):
    def findChangeSourceId(self, name):
        tbl = self.db.model.changesources
        name_hash = self.hashColumns(name)
        return self.findSomethingId(
            tbl=tbl,
            whereclause=(tbl.c.name_hash == name_hash),
            insert_values={"name": name, "name_hash": name_hash},
        )

    # returns a Deferred that returns None
    def setChangeSourceMaster(self, changesourceid, masterid):
        def thd(conn):
            cs_mst_tbl = self.db.model.changesource_masters

            # handle the masterid=None case to get it out of the way
            if masterid is None:
                q = cs_mst_tbl.delete(whereclause=cs_mst_tbl.c.changesourceid == changesourceid)
                conn.execute(q)
                return

            # try a blind insert..
            try:
                q = cs_mst_tbl.insert()
                conn.execute(q, {"changesourceid": changesourceid, "masterid": masterid})
            except (sa.exc.IntegrityError, sa.exc.ProgrammingError) as e:
                # someone already owns this changesource.
                raise ChangeSourceAlreadyClaimedError from e

        return self.db.pool.do(thd)

    @defer.inlineCallbacks
    def getChangeSource(self, changesourceid):
        cs = yield self.getChangeSources(_changesourceid=changesourceid)
        if cs:
            return cs[0]
        return None

    # returns a Deferred that returns a value
    def getChangeSources(self, active=None, masterid=None, _changesourceid=None):
        def thd(conn):
            cs_tbl = self.db.model.changesources
            cs_mst_tbl = self.db.model.changesource_masters

            # handle the trivial case of masterid=xx and active=False
            if masterid is not None and active is not None and not active:
                return []

            join = cs_tbl.outerjoin(cs_mst_tbl, (cs_tbl.c.id == cs_mst_tbl.c.changesourceid))

            # if we're given a _changesourceid, select only that row
            wc = None
            if _changesourceid:
                wc = cs_tbl.c.id == _changesourceid
            else:
                # otherwise, filter with active, if necessary
                if masterid is not None:
                    wc = cs_mst_tbl.c.masterid == masterid
                elif active:
                    wc = cs_mst_tbl.c.masterid != NULL
                elif active is not None:
                    wc = cs_mst_tbl.c.masterid == NULL

            q = sa.select(
                [cs_tbl.c.id, cs_tbl.c.name, cs_mst_tbl.c.masterid], from_obj=join, whereclause=wc
            )

            return [
                {"id": row.id, "name": row.name, "masterid": row.masterid}
                for row in conn.execute(q).fetchall()
            ]

        return self.db.pool.do(thd)
