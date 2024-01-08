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


from twisted.internet import defer

from buildbot.data import base
from buildbot.data import types
from buildbot.util import identifiers


class EndpointMixin:
    def db2data(self, dbdict):
        data = {
            'logid': dbdict['id'],
            'name': dbdict['name'],
            'slug': dbdict['slug'],
            'stepid': dbdict['stepid'],
            'complete': dbdict['complete'],
            'num_lines': dbdict['num_lines'],
            'type': dbdict['type'],
        }
        return defer.succeed(data)


class LogEndpoint(EndpointMixin, base.BuildNestingMixin, base.Endpoint):
    kind = base.EndpointKind.SINGLE
    pathPatterns = """
        /logs/n:logid
        /steps/n:stepid/logs/i:log_slug
        /builds/n:buildid/steps/i:step_name/logs/i:log_slug
        /builds/n:buildid/steps/n:step_number/logs/i:log_slug
        /builders/n:builderid/builds/n:build_number/steps/i:step_name/logs/i:log_slug
        /builders/n:builderid/builds/n:build_number/steps/n:step_number/logs/i:log_slug
        /builders/i:buildername/builds/n:build_number/steps/i:step_name/logs/i:log_slug
        /builders/i:buildername/builds/n:build_number/steps/n:step_number/logs/i:log_slug
    """

    @defer.inlineCallbacks
    def get(self, resultSpec, kwargs):
        if 'logid' in kwargs:
            dbdict = yield self.master.db.logs.getLog(kwargs['logid'])
            return (yield self.db2data(dbdict)) if dbdict else None

        stepid = yield self.getStepid(kwargs)
        if stepid is None:
            return None

        dbdict = yield self.master.db.logs.getLogBySlug(stepid, kwargs.get('log_slug'))
        return (yield self.db2data(dbdict)) if dbdict else None


class LogsEndpoint(EndpointMixin, base.BuildNestingMixin, base.Endpoint):
    kind = base.EndpointKind.COLLECTION
    pathPatterns = """
        /steps/n:stepid/logs
        /builds/n:buildid/steps/i:step_name/logs
        /builds/n:buildid/steps/n:step_number/logs
        /builders/n:builderid/builds/n:build_number/steps/i:step_name/logs
        /builders/n:builderid/builds/n:build_number/steps/n:step_number/logs
        /builders/i:buildername/builds/n:build_number/steps/i:step_name/logs
        /builders/i:buildername/builds/n:build_number/steps/n:step_number/logs
    """

    @defer.inlineCallbacks
    def get(self, resultSpec, kwargs):
        stepid = yield self.getStepid(kwargs)
        if not stepid:
            return []
        logs = yield self.master.db.logs.getLogs(stepid=stepid)
        results = []
        for dbdict in logs:
            results.append((yield self.db2data(dbdict)))
        return results


class Log(base.ResourceType):
    name = "log"
    plural = "logs"
    endpoints = [LogEndpoint, LogsEndpoint]
    keyField = "logid"
    eventPathPatterns = """
        /logs/:logid
        /steps/:stepid/logs/:slug
    """
    subresources = ["LogChunk"]

    class EntityType(types.Entity):
        logid = types.Integer()
        name = types.String()
        slug = types.Identifier(50)
        stepid = types.Integer()
        complete = types.Boolean()
        num_lines = types.Integer()
        type = types.Identifier(1)

    entityType = EntityType(name, 'Log')

    @defer.inlineCallbacks
    def generateEvent(self, _id, event):
        # get the build and munge the result for the notification
        build = yield self.master.data.get(('logs', str(_id)))
        self.produceEvent(build, event)

    @base.updateMethod
    @defer.inlineCallbacks
    def addLog(self, stepid, name, type):
        slug = identifiers.forceIdentifier(50, name)
        while True:
            try:
                logid = yield self.master.db.logs.addLog(
                    stepid=stepid, name=name, slug=slug, type=type
                )
            except KeyError:
                slug = identifiers.incrementIdentifier(50, slug)
                continue
            self.generateEvent(logid, "new")
            return logid

    @base.updateMethod
    @defer.inlineCallbacks
    def appendLog(self, logid, content):
        res = yield self.master.db.logs.appendLog(logid=logid, content=content)
        self.generateEvent(logid, "append")
        return res

    @base.updateMethod
    @defer.inlineCallbacks
    def finishLog(self, logid):
        res = yield self.master.db.logs.finishLog(logid=logid)
        self.generateEvent(logid, "finished")
        return res

    @base.updateMethod
    def compressLog(self, logid):
        return self.master.db.logs.compressLog(logid=logid)
