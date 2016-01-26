"""This module contains async actions."""

import httplib
import logging
import uuid

from tor_async_util import AsyncAction
import tornado.httpclient

from async_docker_remote_api import AsyncImagePuller
from async_docker_remote_api import AsyncContainerLogFetcher
from async_docker_remote_api import AsyncContainerRunner
from async_docker_remote_api import AsyncContainerDeleter
from async_docker_remote_api import AsyncContainerExitWaiter

_logger = logging.getLogger(__name__)


class AsyncEndToEndContainerRunner(AsyncAction):
    """Async'ly ...
    """

    # CFD = Create Failure Details
    CFD_OK = 0x0000
    CFD_ERROR = 0x0080
    CFD_ERROR_PULLING_IMAGE = CFD_ERROR | 0x0001
    CFD_ERROR_RUNNING_CONTAINER = CFD_ERROR | 0x0002
    CFD_WAITING_FOR_CONTAINER_TO_EXIT = CFD_ERROR | 0x0003
    CFD_ERROR_FETCHING_CONTAINER_LOGS = CFD_ERROR | 0x0003

    def __init__(self, docker_image, tag, cmd, async_state=None):
        AsyncAction.__init__(self, async_state)

        self.docker_image = docker_image
        self.tag = tag
        self.cmd = cmd

        self.cid = uuid.uuid4().hex

        self.create_failure_detail = None

        self._container_id = None
        self._exit_code = None
        self._stdout = None
        self._stderr = None
        self._callback = None

    def create(self, callback):
        assert self._callback is None
        self._callback = callback

        fmt = '%s - attempting to pull image %s:%s'
        _logger.info(fmt, self.cid, self.docker_image, self.tag)
        aip = AsyncImagePuller(self.docker_image, self.tag)
        aip.pull(self._on_aip_pull_done)

    def _on_aip_pull_done(self, is_ok, api):
        if not is_ok:
            fmt = '%s - error pulling image %s:%s'
            _logger.error(fmt, self.cid, self.docker_image, self.tag)
            self._call_callback(type(self).CFD_ERROR_PULLING_IMAGE)
            return

        fmt = '%s - successfully pulled image %s:%s'
        _logger.info(fmt, self.cid, self.docker_image, self.tag)

        fmt = '%s - attempting to start container running %s:%s - %s'
        _logger.info(fmt, self.cid, self.docker_image, self.tag, self.cmd)
        arc = AsyncContainerRunner(self.docker_image, self.tag, self.cmd)
        arc.run(self._on_arc_run_done)

    def _on_arc_run_done(self, is_ok, container_id, arc):
        if not is_ok:
            fmt = '%s - error starting container running %s:%s - %s'
            _logger.error(fmt, self.cid, self.docker_image, self.tag, self.cmd)
            self._call_callback(type(self).CFD_ERROR_RUNNING_CONTAINER)
            return

        self._container_id = container_id

        fmt = '%s - successfully started container running %s:%s - %s - container ID = %s'
        _logger.info(fmt, self.cid, self.docker_image, self.tag, self.cmd, self._container_id)

        fmt = '%s - attempting to wait for container to exit - conatiner ID = %s'
        _logger.error(fmt, self.cid, self._container_id)
        acew = AsyncContainerExitWaiter(self._container_id)
        acew.wait(self._on_acew_wait_done)

    def _on_acew_wait_done(self, is_ok, exit_code, acew):
        if not is_ok:
            fmt = '%s - error waiting for container to exit - conatiner ID = %s'
            _logger.error(fmt, self.cid, self._container_id)
            self._call_callback(type(self).CFD_WAITING_FOR_CONTAINER_TO_EXIT)
            return

        self._exit_code = exit_code

        fmt = '%s - container exited - conatiner ID = %s'
        _logger.error(fmt, self.cid, self._container_id)

        fmt = '%s - attempting to fetch container\'s stdout and stderr - container ID = %s'
        _logger.info(fmt, self.cid, self._container_id)
        aclf = AsyncContainerLogFetcher(self._container_id)
        aclf.fetch(self._on_aclf_fetch_done)

    def _on_aclf_fetch_done(self, is_ok, stdout, stderr, aclf):
        if not is_ok:
            fmt = '%s - error fetching container\'s stdout and stderr - container ID = %s'
            _logger.error(fmt, self.cid, self._container_id)
            self._call_callback(type(self).CFD_ERROR_FETCHING_CONTAINER_LOGS)
            return

        self._stdout = stdout
        self._stderr = stderr

        fmt = '%s - successfully fetched container\'s stdout and stderr - container ID = %s'
        _logger.info(fmt, self.cid, self._container_id)

        fmt = '%s - attempting to delete container - container ID = %s'
        _logger.info(fmt, self.cid, self._container_id)
        acd = AsyncContainerDeleter(self._container_id)
        acd.delete(self._on_acd_delete_done)

    def _on_acd_delete_done(self, is_ok, adc):
        if not is_ok:
            fmt = '%s - error deleting container - container ID = %s'
            _logger.error(fmt, self.cid, self._container_id)
            self._call_callback(type(self).CFD_ERROR_RUNNING_CONTAINER)
            return

        fmt = '%s - successfully deleted container - container ID = %s'
        _logger.info(fmt, self.cid, self._container_id)

        self._call_callback(type(self).CFD_OK, self._exit_code, self._stdout, self._stderr)

    def _call_callback(self, create_failure_detail, exit_code=None, stdout=None, stderr=None):
        assert self._callback is not None
        assert self.create_failure_detail is None
        self.create_failure_detail = create_failure_detail
        is_ok = not bool(self.create_failure_detail & type(self).CFD_ERROR)
        self._callback(is_ok, exit_code, stdout, stderr, self)
        self._callback = None


class AsyncDockerRemoteAPIHealthChecker(AsyncAction):
    """Async'ly ...
    """

    # CFD = Create Failure Details
    CFD_OK = 0x0000
    CFD_ERROR = 0x0080
    CFD_ERROR_PULLING_IMAGE = CFD_ERROR | 0x0001

    def __init__(self, docker_image, tag, cmd, async_state=None):
        AsyncAction.__init__(self, async_state)

        self.docker_image = docker_image
        self.tag = tag
        self.cmd = cmd

        self.create_failure_detail = None

        self._callback = None

    def check(self, callback):
        assert self._callback is None
        self._callback = callback

        request = tornado.httpclient.HTTPRequest(
            'http://127.0.0.1:4243/version',
            method='GET')

        http_client = tornado.httpclient.AsyncHTTPClient()
        http_client.fetch(request, callback=self._on_http_client_fetch_done)

    def _on_http_client_fetch_done(self, response):
        self._call_callback(response.code == httplib.OK)

    def _call_callback(self, is_ok):
        assert self._callback is not None
        self._callback(is_ok, self)
        self._callback = None