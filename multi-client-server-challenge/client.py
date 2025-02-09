import socket
import struct
import hashlib
import os
import signal
import sys

SERVER_HOST = '127.0.0.1'
SERVER_PORT = 5001
CHUNK_SIZE = 1024

client_socket = None


def compute_checksum(file_path):
    """Compute SHA256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_all_files(directory):
    """Get all file paths recursively in a directory."""
    file_paths = []
    for root, _, files in os.walk(directory):
        for file in files:
            file_paths.append(os.path.join(root, file))
    return file_paths


def upload_files(files):
    """Handles file upload to the server."""
    global client_socket
    client_socket.send(struct.pack("I", 1))  # Upload operation
    client_socket.send(struct.pack("I", len(files)))  # Number of files

    for file_path in files:
        relative_path = os.path.relpath(file_path, start=os.path.dirname(files[0]))  # Keep relative structure
        client_socket.send(struct.pack("I", len(relative_path)))
        client_socket.send(relative_path.encode())

        file_size = os.path.getsize(file_path)
        client_socket.send(struct.pack("Q", file_size))

        with open(file_path, "rb") as f:
            while chunk := f.read(CHUNK_SIZE):
                client_socket.send(chunk)

        server_checksum = client_socket.recv(64).decode()
        client_checksum = compute_checksum(file_path)
        client_socket.send(client_checksum.encode())

        if client_checksum == server_checksum:
            print(f"[✔] {relative_path} uploaded successfully ✅")
        else:
            print(f"[-] {relative_path} checksum mismatch ❌")


def download_file(file_name, save_dir):
    """Handles file download from the server."""
    global client_socket
    client_socket.send(struct.pack("I", 2))  # Download operation
    client_socket.send(struct.pack("I", len(file_name)))
    client_socket.send(file_name.encode())

    file_size = struct.unpack("Q", client_socket.recv(8))[0]

    if file_size == 0:
        print(f"[-] File not found on server: {file_name}")
        return

    save_path = os.path.join(save_dir, file_name)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    with open(save_path, "wb") as f:
        while file_size > 0:
            chunk = client_socket.recv(min(CHUNK_SIZE, file_size))
            f.write(chunk)
            file_size -= len(chunk)

    server_checksum = client_socket.recv(64).decode()
    client_checksum = compute_checksum(save_path)
    client_socket.send(client_checksum.encode())

    if client_checksum == server_checksum:
        print(f"[✔] {file_name} downloaded successfully ✅")
    else:
        print(f"[-] {file_name} checksum mismatch ❌")


def exit_gracefully(signal_received, frame):
    """Handles CTRL+C (SIGINT) to exit the client cleanly."""
    print("\n[+] Exiting client...")
    if client_socket:
        client_socket.close()
    sys.exit(0)


def main():
    global client_socket
    signal.signal(signal.SIGINT, exit_gracefully)

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((SERVER_HOST, SERVER_PORT))
    print(f"[+] Connected to server at {SERVER_HOST}:{SERVER_PORT}")

    choice = input("Enter folder path to upload: ").strip()
    if os.path.isdir(choice):
        files = get_all_files(choice)
        upload_files(files)
    else:
        print("[-] Invalid folder path.")

    exit_gracefully(None, None)


if __name__ == "__main__":
    main()
