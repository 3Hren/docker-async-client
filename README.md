Docker Asynchronous Client
==========================

Using tornado inside.

Supported methods:

* Info
* Containers
* Images
* Build
* Push


## Example:

```python
from tornado.ioloop import IOLoop

import docker


def handle(future):
    print(future.result())
    io_loop.stop()


if __name__ == '__main__':
    io_loop = IOLoop.instance()
    client = docker.Client()
    future = client.info()
    io_loop.add_future(future, handle)
    io_loop.start()
```


