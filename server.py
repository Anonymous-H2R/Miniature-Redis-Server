from gevent import socket
from gevent.pool import Pool
from gevent.server import StreamServer
from collections import namedtuple
from io import BytesIO
from socket import error as socket_error

class CommandError(Exception): pass
class Disconnect(Exception): pass

Error=namedtuple('Error',('message',))

class ProtocolHandler:
    def __init__(self):
        self.handlers={
            b'+':self.handle_simple_string,
            b'-':self.handle_error,
            b':':self.handle_integer,
            b'$':self.handle_string,
            b'*':self.handle_array,
            b'%':self.handle_dict,
        }

    def handle_request(self,socket_file):
        first_byte=socket_file.read(1)
        if not first_byte:
            raise Disconnect()
        try:
            return self.handlers[first_byte](socket_file)
        except KeyError:
            raise CommandError('bad request')

    def handle_simple_string(self,socket_file):
        return socket_file.readline().rstrip(b'\r\n')

    def handle_error(self,socket_file):
        return Error(socket_file.readline().rstrip(b'\r\n'))

    def handle_integer(self,socket_file):
        return int(socket_file.readline().rstrip(b'\r\n'))

    def handle_string(self,socket_file):
        length=int(socket_file.readline().rstrip(b'\r\n'))
        if length==-1:
            return None
        return socket_file.read(length+2)[:-2]

    def handle_array(self,socket_file):
        num_elements=int(socket_file.readline().rstrip(b'\r\n'))
        return [self.handle_request(socket_file) for _ in range(num_elements)]

    def handle_dict(self,socket_file):
        num_items=int(socket_file.readline().rstrip(b'\r\n'))
        elements=[self.handle_request(socket_file) for _ in range(num_items*2)]
        return dict(zip(elements[::2],elements[1::2]))

    def write_response(self,socket_file,data):
        buf=BytesIO()
        self._write(buf,data)
        buf.seek(0)
        socket_file.write(buf.getvalue())
        socket_file.flush()

    def _write(self,buf,data):
        if isinstance(data,str):
            data=data.encode('utf-8')
        if isinstance(data,bytes):
            buf.write(('$%s\r\n'%len(data)).encode()+data+ b'\r\n')
        elif isinstance(data,int):
            buf.write((':%s\r\n' % data).encode())
        elif isinstance(data,Error):
            buf.write(('-%s\r\n' % data.message).encode())
        elif isinstance(data,(list,tuple)):
            buf.write(('*%s\r\n' %len(data)).encode())
            for item in data:
                self._write(buf,item)
        elif isinstance(data,dict):
            buf.write(('%%%s\r\n' %len(data)).encode())
            for key,val in data.items():
                self._write(buf,key)
                self._write(buf, val)
        elif data is None:
            buf.write(b'$-1\r\n')
        else:
            raise CommandError('unrecognized type:%s'% type(data))

class Server:
    def __init__(self,host='127.0.0.1',port=31337,max_clients=64):
        self._pool=Pool(max_clients)
        self._server=StreamServer((host,port),self.connection_handler,spawn=self._pool)
        self._protocol=ProtocolHandler()
        self._kv={}
        self._commands={
            'GET':self.get,'SET':self.set,'DELETE':self.delete,
            'FLUSH':self.flush,'MGET':self.mget,'MSET':self.mset,
        }

    def connection_handler(self, conn, address):
        socket_file_r = conn.makefile('rb')
        socket_file_w = conn.makefile('wb')
        while True:
            try:
                data = self._protocol.handle_request(socket_file_r)
            except Disconnect:
                break
            try:
                resp = self.get_response(data)
            except CommandError as exc:
                resp = Error(exc.args[0])
            self._protocol.write_response(socket_file_w, resp)

    def get_response(self,data):
        if not isinstance(data,list):
            try:
                data=data.split()
            except:
                raise CommandError('Request must be list or simple string.')

        if not data:
            raise CommandError('Missing command')
        command=data[0].upper()
        if isinstance(command,bytes):
            command=command.decode()
        if command not in self._commands:
            raise CommandError('Unrecognized command:%s'%command)
        return self._commands[command](*data[1:])

    def get(self,key):
        return self._kv.get(key)
    def set(self,key,value):
        self._kv[key]=value
        return 1

    def delete(self,key):
        if key in self._kv:
            del self._kv[key]
            return 1
        return 0
    def flush(self):
        n=len(self._kv)
        self._kv.clear()
        return n
    def mget(self,*keys):
        return [self._kv.get(k)for k in keys]
    def mset(self,*items):
        pairs=list(zip(items[::2],items[1::2]))
        for k,v in pairs:
            self._kv[k]=v
        return len(pairs)

    def run(self):
        self._server.serve_forever()


class Client:
    def __init__(self,host='127.0.0.1',port=31337):
        self._protocol=ProtocolHandler()
        self._socket=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self._socket.connect((host,port))
        self._fh_write = self._socket.makefile('wb')
        self._fh = self._socket.makefile('rb')

    def execute(self, *args):
        self._protocol.write_response(self._fh_write, args)
        resp = self._protocol.handle_request(self._fh)
        if isinstance(resp, Error):
            raise CommandError(resp.message)
        return resp

    def get(self,key):
        return self.execute('GET',key)

    def set(self,key,value):
        return self.execute('SET',key,value)

    def delete(self,key):
        return self.execute('DELETE',key)

    def flush(self):
        return self.execute('FLUSH')

    def mget(self,*keys):
        return self.execute('MGET',*keys)

    def mset(self,*items):
        return self.execute('MSET',*items)

if __name__ == '__main__':
    from gevent import monkey; monkey.patch_all()
    Server().run()