import socket

# Network Config
MY_IP = "10.1.37.194"  # Your IP
PORT = 5142  # Same port as your video call app

# Create UDP socket
server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_socket.bind((MY_IP, PORT))

print(f"Server running on {MY_IP}:{PORT}. Waiting for ping...")

while True:
    # Receive data (up to 1024 bytes)
    data, addr = server_socket.recvfrom(1024)
    print(f"Received '{data.decode()}' from {addr}")
    
    # Send response back
    server_socket.sendto(b"pong", addr)
    print(f"Sent 'pong' back to {addr}")