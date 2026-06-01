# Miniature Redis Server

A Redis-like in-memory key-value server built from scratch in Python.

## Features
- Custom binary wire protocol over raw TCP sockets
- 6 supported data types: strings, arrays, integers, dicts, errors, null
- Concurrent client handling via Gevent greenlets (64 client pool)
- Non-blocking I/O using cooperative multitasking
- Commands: GET, SET, DELETE, FLUSH, MGET, MSET

## Run the server
pip install gevent
python server.py

## Run the client
python
from server import Client
c = Client()
c.set('name', 'Alice')  # → 1
c.get('name')           # → b'Alice'
