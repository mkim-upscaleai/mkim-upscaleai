import http.server
import socket
import socketserver

PORT = 8080
Handler = http.server.SimpleHTTPRequestHandler

class TCPServerV6(socketserver.TCPServer):
    address_family = socket.AF_INET6

httpd = TCPServerV6(("::", PORT), Handler)

print(("serving on IPv6 port", PORT))
httpd.serve_forever()
