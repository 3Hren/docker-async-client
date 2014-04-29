from tornado.ioloop import IOLoop

import docker

__author__ = 'Evgeny Safronov <division494@gmail.com>'


def handle(future):
    print(future.result())
    io_loop.stop()


if __name__ == '__main__':
    io_loop = IOLoop.instance()
    client = docker.Client()
    io_loop.add_future(client.info(), handle)
    io_loop.start()
