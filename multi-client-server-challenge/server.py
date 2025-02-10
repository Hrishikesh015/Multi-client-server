import socket
import threading
import os
import struct
import hashlib
import signal
import sys
import zlib

SERVER_HOST = '0.0.0.0'
SERVER_PORT = 5001
CHUNK_SIZE = 1024
UPLOAD_DIR = "uploads"

# Ensure upload directory exists
os.makedirs(UPLOAD_DIR, exist_ok=True)

server_socket = None
shutdown_event = threading.Event()


def compute_checksum(file_path):
    """Compute SHA256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            sha256.update(chunk)
    return sha256.hexdigest()


def handle_client(client_socket, client_id):
    try:
        print(f"[+] [Client {client_id}] Connected.")

        while True:
            operation_data = client_socket.recv(4)
            if not operation_data:
                break  # Exit loop if the client disconnects

            operation = struct.unpack("I", operation_data)[0]

            if operation == 1:  # Upload
                    num_files = struct.unpack("I", client_socket.recv(4))[0]

                    for _ in range(num_files):
                        path_length = struct.unpack("I", client_socket.recv(4))[0]
                        file_path = client_socket.recv(path_length).decode()
                        server_file_path = os.path.join(UPLOAD_DIR, f"client_{client_id}", file_path)
                        os.makedirs(os.path.dirname(server_file_path), exist_ok=True)

                        file_size = struct.unpack("Q", client_socket.recv(8))[0]

                        with open(server_file_path, "wb") as f:
                            while file_size > 0:
                                chunk = client_socket.recv(min(CHUNK_SIZE, file_size))
                                f.write(chunk)
                                file_size -= len(chunk)

                        server_checksum = compute_checksum(server_file_path)
                        client_socket.send(server_checksum.encode())

                        client_checksum = client_socket.recv(64).decode()
                        if client_checksum == server_checksum:
                            print(f"[✔] [Client {client_id}] {file_path} received successfully ✅")
                        else:
                            print(f"[-] [Client {client_id}] {file_path} checksum mismatch ❌")
            elif operation == 2:  # Download
                try:
                    path_length = struct.unpack("I", client_socket.recv(4))[0]
                    file_name = client_socket.recv(path_length).decode()
                    file_path = os.path.join(UPLOAD_DIR, file_name)

                    if not os.path.exists(file_path):
                        client_socket.send(struct.pack("Q", 0))  # File not found
                        return

                    file_size = os.path.getsize(file_path)
                    client_socket.send(struct.pack("Q", file_size))

                    with open(file_path, "rb") as f:
                        while chunk := f.read(CHUNK_SIZE):
                            client_socket.send(chunk)

                    server_checksum = compute_checksum(file_path)
                    client_socket.send(server_checksum.encode())

                    client_checksum = client_socket.recv(64).decode()
                    if client_checksum == server_checksum:
                        print(f"[✔] {file_name} sent successfully ✅")
                    else:
                        print(f"[-] {file_name} checksum mismatch ❌")

                except Exception as e:
                    print(f"[-] [Client {client_id}] Error: {e}")

                finally:
                    client_socket.close()
            

            elif operation == 3:  # List files
                file_list = [os.path.relpath(os.path.join(root, f), UPLOAD_DIR) for root, _, files in os.walk(UPLOAD_DIR) for f in files]
                client_socket.send(struct.pack("I", len(file_list)))
                for file in file_list:
                    client_socket.send(struct.pack("I", len(file)))
                    client_socket.send(file.encode())

            elif operation == 4:  # Exit
                client_socket.close()
                print(f"[!] [Client {client_id}] Disconnected.")
                break

    except Exception as e:
        print(f"[-] [Client {client_id}] Error: {e}")

    finally:
        client_socket.close()



def exit_gracefully(signal_received, frame):
    """Handles CTRL+C (SIGINT) to stop the server cleanly"""
    print("\n[+] [Server] Shutting down gracefully...")
    shutdown_event.set()
    if server_socket:
        server_socket.close()
    sys.exit(0)


def main():
    global server_socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((SERVER_HOST, SERVER_PORT))
    server_socket.listen(5)
    server_socket.settimeout(1)

    print(f"[+] Server listening on {SERVER_HOST}:{SERVER_PORT}")

    signal.signal(signal.SIGINT, exit_gracefully)

    client_id = 0
    while not shutdown_event.is_set():
        try:
            client_socket, addr = server_socket.accept()
            print(f"[+] New connection from {addr}, assigned Client ID: {client_id}")
            threading.Thread(target=handle_client, args=(client_socket, client_id), daemon=True).start()
            client_id += 1
        except socket.timeout:
            continue

    print("[+] [Server] Exiting...")
    server_socket.close()


if __name__ == "__main__":
    main()
