#! /usr/bin/env python3
# Copied from https://www.bogotobogo.com/python/python_network_programming_tcp_server_client_chat_server_chat_client_select.php
# ... and then modified

# chat_server.py
 
import sys, socket, select

HOST = '' 
SOCKET_LIST = []
RECV_BUFFER = 4096 

def chat_server():

    if len(sys.argv) > 1:
        try:
            PORT = int(sys.argv[1])
        except:
            print("Accepts one optional arg, a port number.")
            return 1
    else:
        PORT = 15000
        print("Using default port.")

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen()
 
    # add server socket object to the list of readable connections
    SOCKET_LIST.append(server_socket)
 
    print("Chat server started on port " + str(PORT))
 
    while 1:

        # get the list sockets which are ready to be read through select
        try:
            ready_to_read,ready_to_write,in_error = select.select(SOCKET_LIST,[],[])
        except KeyboardInterrupt:
            break
      
        for sock in ready_to_read:
            # a new connection request recieved
            if sock == server_socket: 
                sock, addr = server_socket.accept()
                addr = str(addr)
                SOCKET_LIST.append(sock)
                print("%s connected" % addr)
                 
            # a message from a client, not a new connection
            else:
                # process data recieved from client, 
                try:
                    # receiving data from the socket.
                    data = sock.recv(RECV_BUFFER)
                    if data:
                        # there is something in the socket
                        broadcast(server_socket, data)  
                    else:
                        # remove the socket that's broken    
                        peer = str(sock.getpeername())
                        sock.close()
                        SOCKET_LIST.remove(sock)

                        # at this stage, no data means probably the connection has been broken
                        print("%s disconnected" % peer)

                # exception 
                except:
                    try:
                        sock.close()
                    except:
                        pass # TODO be more descriptive
                    SOCKET_LIST.remove(sock)

    for sock in SOCKET_LIST:
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()
    
# broadcast chat messages to all connected clients
def broadcast (server_socket, message):
    if isinstance(message, str):
        message = message.encode('utf-8')
    for socket in SOCKET_LIST:
        # send the message only to peer
        if socket != server_socket:
            try:
                socket.send(message)
            except:
                # broken socket connection
                print("Failed sending, disconnecting %s" % str(socket.getpeername()))
                try:
                    socket.close()
                except:
                    pass # TODO be more verbose
                SOCKET_LIST.remove(socket)
 
if __name__ == "__main__":
    sys.exit(chat_server())
