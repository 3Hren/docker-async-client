import base64
import json
import logging
import os
import tarfile
import urllib

import StringIO

from tornado.gen import Return, coroutine
from tornado.httpclient import AsyncHTTPClient, HTTPRequest
from tornado.httputil import HTTPHeaders
from tornado.ioloop import IOLoop

from .internal._unix import AsyncUnixHTTPClient

__author__ = 'Evgeny Safronov <division494@gmail.com>'


DEFAULT_TIMEOUT = 3600.0
DEFAULT_URL = 'unix://var/run/docker.sock'
DEFAULT_VERSION = '1.7'
DEFAULT_INDEX_URL = 'https://index.docker.io/v1/'


log = logging.getLogger(__name__)


def expand_registry_url(hostname):
    if hostname.startswith('http:') or hostname.startswith('https:'):
        if '/' not in hostname[9:]:
            hostname += '/v1/'
        return hostname
    return 'http://' + hostname + '/v1/'


def resolve_repository_name(fullname):
    if '://' in fullname:
        raise ValueError('repository name can not contain a scheme ({0})'.format(fullname))

    parts = fullname.split('/', 1)
    if '.' not in parts[0] and ':' not in parts[0] and parts[0] != 'localhost':
        return DEFAULT_INDEX_URL, fullname

    if len(parts) < 2:
        raise ValueError('invalid repository name ({0})'.format(fullname))

    if 'index.docker.io' in parts[0]:
        raise ValueError('invalid repository name, try "{0}" instead'.format(parts[1]))

    return expand_registry_url(parts[0]), parts[1]


class Client(object):
    def __init__(self, url=DEFAULT_URL, version=DEFAULT_VERSION, timeout=DEFAULT_TIMEOUT, io_loop=None):
        self.url = url
        self.version = version
        self.timeout = timeout
        self._config = {
            'url': url,
            'version': version,
            'timeout': timeout,
            'io_loop': io_loop
        }

    def info(self):
        return Info(**self._config).execute()

    def images(self):
        return Images(**self._config).execute()

    def containers(self):
        return Containers(**self._config).execute()

    def build(self, path, tag=None, quiet=False, streaming=None):
        return Build(path, tag, quiet, streaming, **self._config).execute()

    def push(self, name, auth, streaming=None):
        return Push(name, auth, streaming, **self._config).execute()


class Action(object):
    def __init__(self, url, version, timeout=DEFAULT_TIMEOUT, io_loop=None):
        self._unix = url.startswith('unix://')
        self._version = version
        self.timeout = timeout
        if self._unix:
            self._base_url = url
            self._http_client = AsyncUnixHTTPClient(io_loop, url)
        else:
            self._base_url = '{0}/v{1}'.format(url, version)
            self._http_client = AsyncHTTPClient(io_loop)

    def execute(self):
        raise NotImplementedError

    def _make_url(self, path, query=None):
        if query is not None:
            query = dict((k, v) for k, v, in query.iteritems() if v is not None)
            return '{0}{1}?{2}'.format(self._base_url, path, urllib.urlencode(query))
        else:
            return '{0}{1}'.format(self._base_url, path)


class Info(Action):
    @coroutine
    def execute(self):
        response = yield self._http_client.fetch(self._make_url('/info'))
        raise Return(json.loads(response.body))


class Images(Action):
    @coroutine
    def execute(self):
        response = yield self._http_client.fetch(self._make_url('/images/json'))
        raise Return(json.loads(response.body))


class Containers(Action):
    @coroutine
    def execute(self):
        response = yield self._http_client.fetch(self._make_url('/containers/json'))
        raise Return(json.loads(response.body))


class Build(Action):
    def __init__(self, path, tag=None, quiet=False, streaming=None,
                 url=DEFAULT_URL, version=DEFAULT_VERSION, timeout=DEFAULT_TIMEOUT, io_loop=None):
        super(Build, self).__init__(url, version, timeout, io_loop)
        self._path = path
        self._tag = tag
        self._quiet = quiet
        self._streaming = streaming or self._save
        self._chunks = []
        self._io_loop = io_loop or IOLoop.current()

    @coroutine
    def execute(self):
        headers = None
        body = ''
        remote = None

        if any(map(self._path.startswith, ['http://', 'https://', 'git://', 'github.com/'])):
            log.info('Remote url detected: "%s"', self._path)
            remote = self._path
        else:
            log.info('Local path detected.')
            if not os.path.exists(self._path):
                raise ValueError('Path not exists: %s'.format(self._path))

            log.info('Checking Dockerfile in "%s" ...', self._path)
            if not os.path.exists(os.path.join(self._path, "Dockerfile")):
                raise ValueError('Dockerfile not found: "{0}"'.format(os.path.abspath(self._path)))

            log.info('Creating archive "%s"... ', self._path)
            body = self._tar(self._path)
            headers = {'Content-Type': 'application/tar'}

        query = {'t': self._tag, 'remote': remote, 'q': self._quiet}
        url = self._make_url('/build', query)
        log.info('Building "%s"... ', url)
        request = HTTPRequest(url,
                              method='POST', headers=headers, body=body,
                              request_timeout=self.timeout,
                              streaming_callback=self._streaming)
        try:
            yield self._http_client.fetch(request)
            log.info('Image has been successfully built.')
        except Exception as err:
            log.info('Failed to build image - %s', err)
            raise err

        raise Return(''.join(self._chunks))

    def _save(self, chunk):
        self._chunks.append(chunk)

    def _tar(self, path):
        stream = StringIO.StringIO()
        try:
            tar = tarfile.open(mode='w', fileobj=stream)
            tar.add(path, arcname='.')
            return stream.getvalue()
        finally:
            stream.close()


class Push(Action):
    def __init__(self, name, auth, streaming=None,
                 url=DEFAULT_URL, version=DEFAULT_VERSION, timeout=DEFAULT_TIMEOUT, io_loop=None):
        self.name = name
        self.auth = auth
        self._streaming = streaming or self._save
        self._chunks = []
        super(Push, self).__init__(url, version, timeout, io_loop)

    @coroutine
    def execute(self):
        url = self._make_url('/images/{0}/push'.format(self.name))
        registry, name = resolve_repository_name(self.name)

        headers = HTTPHeaders()
        headers.add('X-Registry-Auth', self._prepare_auth_header_value())
        body = ''
        log.info('Pushing "%s" into "%s"... ', name, registry)
        request = HTTPRequest(url, method='POST',
                              headers=headers,
                              body=body,
                              request_timeout=self.timeout,
                              streaming_callback=self._on_body)
        try:
            yield self._http_client.fetch(request)
            log.info('Successfully pushed "%s" image.', self.name)
        except Exception as err:
            log.error('Failed to push image "%s" - %r', self.name, err)
            raise err

        raise Return(''.join(self._chunks))

    def _save(self, chunk):
        self._chunks.append(chunk)

    def _prepare_auth_header_value(self):
        username = self.auth.get('username', 'username')
        password = self.auth.get('password, password')
        return base64.b64encode('{0}:{1}'.format(username, password))

    def _on_body(self, data):
        parsed = '<undefined>'
        try:
            response = json.loads(data)
        except ValueError:
            parsed = data
        except Exception as err:
            parsed = 'Unknown error: {0}'.format(err)
        else:
            parsed = self._match_first(response, ['status', 'error'], data)
        finally:
            self._streaming(parsed)

    def _match_first(self, dict_, keys, default):
        for key in keys:
            value = dict_.get(key)
            if value is not None:
                return value
        return default
