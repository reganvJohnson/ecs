"""This module contains a collection of unit tests which
validate ..main
"""

from ConfigParser import ConfigParser
import os
import sys
import tempfile
import unittest

import mock
import tornado.httpserver

from ..main import Main


class Patcher(object):
    """An abstract base class for all patcher context managers."""

    def __init__(self, patcher):
        object.__init__(self)
        self._patcher = patcher

    def __enter__(self):
        self._patcher.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._patcher.stop()


class IsLibcurlCompiledWithAsyncDNSResolverPatcher(Patcher):
    """This context manager provides an easy way to install a
    patch allowing the caller to determine the behavior of
    tor_async_util.is_libcurl_compiled_with_async_dns_resolver().
    """

    def __init__(self, response):

        def the_patch(*args, **kwargs):
            return response

        patcher = mock.patch(
            'tor_async_util.is_libcurl_compiled_with_async_dns_resolver',
            the_patch)

        Patcher.__init__(self, patcher)


class TornadoIOLoopInstancePatcher(object):
    """this class uses an approach to patching with feels somewhat
    barbaric given that mock isn't used. the appoach was used because
    I couldn't figure out how to use mock to patch a static method.
    """

    def __init__(self):
        object.__init__(self)

        self._old_instance_static_method = None

    def __enter__(self):
        assert self._old_instance_static_method is None
        self._old_instance_static_method = tornado.ioloop.IOLoop.instance
        tornado.ioloop.IOLoop.instance = mock.Mock()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        tornado.ioloop.IOLoop.instance = self._old_instance_static_method
        self._old_instance_static_method = None


class TornadoHttpServerListenPatcher(object):
    """this class uses an approach to patching with feels somewhat
    barbaric given that mock isn't used. the appoach was used because
    I couldn't figure out how to use mock to patch a static method.
    """

    def __init__(self):
        object.__init__(self)

        self._old_listen_static_method = None

    def __enter__(self):
        assert self._old_listen_static_method is None
        self._old_listen_static_method = tornado.httpserver.HTTPServer.listen
        tornado.httpserver.HTTPServer.listen = mock.Mock()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        tornado.httpserver.HTTPServer.listen = self._old_listen_static_method
        self._old_listen_static_method = None


class ServiceConfigFile(object):

    def __init__(self, section):
        object.__init__(self)

        self.section = section

        self.filename = None

    def __str__(self):
        return str(self.filename)

    def __enter__(self):
        assert self.filename is None

        cp = ConfigParser()
        cp.add_section(self.section)

        cp.set(self.section, 'address', '127.0.0.1')
        cp.set(self.section, 'port', 8448)
        cp.set(self.section, 'log_level', 'debug')
        cp.set(self.section, 'max_concurrent_executing_http_requests', 250)
        cp.set(self.section, 'docker_remote_api', 'http://127.0.0.1:5000')
        cp.set(self.section, 'docker_remote_api_connect_timeout', 50)
        cp.set(self.section, 'docker_remote_api_request_timeout', 500)

        self.filename = tempfile.mktemp()
        with open(self.filename, 'w+') as fp:
            cp.write(fp)

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.filename:
            if os.path.exists(self.filename):
                os.unlink(self.filename)
                self.filename = None


class SysDotArgcPatcher(object):

    def __init__(self, sys_dot_argv):
        object.__init__(self)

        self.sys_dot_argv = sys_dot_argv
        self._old_sys_dot_argv = None

    def __enter__(self):
        assert self._old_sys_dot_argv is None

        self._old_sys_dot_argv = None
        sys.argv = self.sys_dot_argv

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        sys.argv = self._old_sys_dot_argv
        self._old_sys_dot_argv = None


class MainTestCase(unittest.TestCase):

    def test_libcurl_async_dns_resolver(self):
        config_section = 'boo'
        with ServiceConfigFile(config_section) as service_config_file:
            sys_dot_arv = [
                'service',
                '--config=%s' % service_config_file,
            ]
            with SysDotArgcPatcher(sys_dot_arv):
                with TornadoHttpServerListenPatcher():
                    with TornadoIOLoopInstancePatcher():
                        with IsLibcurlCompiledWithAsyncDNSResolverPatcher(True):
                            main = Main()
                            main.configure()
                        with IsLibcurlCompiledWithAsyncDNSResolverPatcher(False):
                            main = Main()
                            main.configure()

    def test_happy_path(self):
        config_section = 'boo'
        with ServiceConfigFile(config_section) as service_config_file:
            sys_dot_arv = [
                'service',
                '--config=%s' % service_config_file,
            ]
            with SysDotArgcPatcher(sys_dot_arv):
                with TornadoHttpServerListenPatcher():
                    with TornadoIOLoopInstancePatcher():
                        main = Main()
                        main.configure()
                        main.listen()
