

import socket
import struct
import hashlib
import os
import signal
import sys
import multiprocessing.shared_memory as shm
import multiprocessing
import tempfile


SERVER_HOST = '0.0.0.0'
SERVER_PORT = 5001
CHUNK_SIZE = 1024
UPLOAD_DIR = "uploads"

os.makedirs(UPLOAD_DIR, exist_ok=True)
server_socket = None
shutdown_event = multiprocessing.Event()

def compute_checksum(data):
    """Computes SHA-256 checksum of data (bytes or file path)."""
    sha256 = hashlib.sha256()
    if isinstance(data, str):
        with open(data, "rb") as f:
            while chunk := f.read(CHUNK_SIZE):
                sha256.update(chunk)
    else:
        sha256.update(data)
    return sha256.hexdigest()

def upload_file(client_socket, upload_shared_mem, client_id, client_dir):
    """Handles file uploads using shared memory."""
    try:
        num_files = struct.unpack("I", client_socket.recv(4))[0]
        for _ in range(num_files):
            path_length = struct.unpack("I", client_socket.recv(4))[0]
            file_path = client_socket.recv(path_length).decode()
            temp_file_path = os.path.join(tempfile.gettempdir(), f"temp_{client_id}_{file_path}")

            file_size = struct.unpack("Q", client_socket.recv(8))[0]
            with open(temp_file_path, "wb") as f:
                while file_size > 0:
                    chunk = client_socket.recv(min(CHUNK_SIZE, file_size))
                    upload_shared_mem.buf[:len(chunk)] = chunk
                    received_checksum = client_socket.recv(64).decode()
                    if received_checksum == compute_checksum(chunk):
                        f.write(upload_shared_mem.buf[:len(chunk)])
                        file_size -= len(chunk)
                        client_socket.send(b"ACK")
                    else:
                        client_socket.send(b"RETRY")

            final_path = os.path.join(client_dir, file_path)
            os.makedirs(os.path.dirname(final_path), exist_ok=True)
            os.replace(temp_file_path, final_path)

            server_checksum = compute_checksum(final_path)
            client_socket.send(server_checksum.encode())
            client_checksum = client_socket.recv(64).decode()
            if client_checksum == server_checksum:
                print(f"[✔] [Client {client_id}] {file_path} received successfully ✅")
            else:
                print(f"[-] [Client {client_id}] {file_path} checksum mismatch ❌")
    except Exception as e:
        print(f"Error {e} occured in upload operation")

def download_file(client_socket, download_shared_mem, client_id, client_dir):
    """Handles file downloads using shared memory."""
    try:
        path_length = struct.unpack("I", client_socket.recv(4))[0]
        file_name = client_socket.recv(path_length).decode()
        file_path = os.path.join(client_dir, file_name)
        if not os.path.exists(file_path):
            client_socket.send(struct.pack("Q", 0))
            return
        file_size = os.path.getsize(file_path)
        client_socket.send(struct.pack("Q", file_size))
        with open(file_path, "rb") as f:
            while chunk := f.read(CHUNK_SIZE):
                download_shared_mem.buf[:len(chunk)] = chunk
                chunk_checksum = compute_checksum(chunk).encode()
                client_socket.send(download_shared_mem.buf[:len(chunk)])
                client_socket.send(chunk_checksum)
                response = client_socket.recv(5).decode()
                while response == "RETRY":
                    client_socket.send(download_shared_mem.buf[:len(chunk)])
                    client_socket.send(chunk_checksum)
                    response = client_socket.recv(5).decode()
        server_checksum = compute_checksum(file_path)
        client_socket.send(server_checksum.encode())
        client_checksum = client_socket.recv(64).decode()
        if client_checksum == server_checksum:
            print(f"[✔] [Client {client_id}] {file_name} sent successfully ✅")
        else:
            print(f"[-] [Client {client_id}] checksum mismatch ❌")
    except Exception as e:
        print(f"Error {e} occured at download operation")

def list_files(client_socket, client_id):
    """Handles listing of files for a client."""
    client_dir = os.path.join(UPLOAD_DIR, f"client_{client_id}")
    file_list = [os.path.relpath(os.path.join(root, f), client_dir) for root, _, files in os.walk(client_dir) for f in files]
    client_socket.send(struct.pack("I", len(file_list)))
    for file in file_list:
        client_socket.send(struct.pack("I", len(file)))
        client_socket.send(file.encode())

def handle_client(client_socket, client_id, shared_mem_name):
    """Handles client operations."""
    try:
        print(f"[+] [Client {client_id}] Connected.")
        client_dir = os.path.join(UPLOAD_DIR, f"client_{client_id}")
        os.makedirs(client_dir, exist_ok=True)
        upload_shared_mem = shm.SharedMemory(create=True, size=CHUNK_SIZE, name=f"{shared_mem_name}_upload")
        download_shared_mem = shm.SharedMemory(create=True, size=CHUNK_SIZE, name=f"{shared_mem_name}_download")
        
        while True:
            operation_data = client_socket.recv(4)
            if not operation_data:
                break
            operation = struct.unpack("I", operation_data)[0]

            if operation == 1:
                upload_file(client_socket, upload_shared_mem, client_id, client_dir)
            elif operation == 2:
                download_file(client_socket, download_shared_mem, client_id, client_dir)
            elif operation == 3:
                list_files(client_socket, client_id)
            elif operation == 4:
                print(f"[!] [Client {client_id}] Disconnected.")
                break
    except Exception as e:
        print(f"[-] [Client {client_id}] Error: {e}")
    finally:
        upload_shared_mem.close()
        upload_shared_mem.unlink()
        download_shared_mem.close()
        download_shared_mem.unlink()
        client_socket.close()

def exit_gracefully(signal_received, frame):
    """Handles server shutdown."""
    print("\n[+] [Server] Shutting down gracefully...")
    shutdown_event.set()
    if server_socket:
        server_socket.close()
    sys.exit(0)

def main():
    """Main server function to accept client connections."""
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
            shared_mem_name = f"client_shm_{client_id}"
            process = multiprocessing.Process(target=handle_client, args=(client_socket, client_id, shared_mem_name), daemon=True)
            process.start()
            client_id += 1
        except socket.timeout:
            continue
    
    print("[+] [Server] Exiting...")
    server_socket.close()

if __name__ == "__main__":
    main()
