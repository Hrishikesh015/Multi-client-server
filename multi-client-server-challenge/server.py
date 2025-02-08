import socket
import os
import threading
import sys

CHUNK_SIZE = 4096
SERVER_IP = "0.0.0.0"
SERVER_PORT = 5000
BASE_DIR = "server"
running = True  # Control flag for stopping server

os.makedirs(BASE_DIR, exist_ok=True)

# Track client threads
client_threads = []
server_socket = None  # Declare globally for cleanup


def handle_client(client_socket, client_address):
    """Handle client connection for file uploads & retrievals."""
    client_id = f"{client_address[0]}_{client_address[1]}"
    client_dir = os.path.join(BASE_DIR, client_id)
    os.makedirs(client_dir, exist_ok=True)

    print(f"[+] Client {client_id} connected.")

    try:
        while True:
            command = client_socket.recv(256).decode().strip()
            if not command:
                break

            if command.startswith("UPLOAD"):
                _, filename = command.split(" ", 1)
                file_path = os.path.join(client_dir, filename)
                print(f"[+] Receiving '{filename}' from {client_id}...")

                with open(file_path, "wb") as f:
                    while True:
                        chunk = client_socket.recv(CHUNK_SIZE)
                        if chunk.endswith(b"EOF"):
                            f.write(chunk[:-3])  # Remove EOF marker
                            break
                        f.write(chunk)

                print(f"[✔] File '{filename}' saved at {file_path}")
                client_socket.sendall(b"UPLOAD_SUCCESS")

            elif command.startswith("RETRIEVE"):
                _, filename = command.split(" ", 1)
                file_path = os.path.join(client_dir, filename)

                if not os.path.exists(file_path):
                    client_socket.sendall(b"ERROR: File not found")
                    continue

                print(f"[+] Sending '{filename}' to {client_id}...")

                with open(file_path, "rb") as f:
                    while chunk := f.read(CHUNK_SIZE):
                        client_socket.sendall(chunk)

                client_socket.sendall(b"EOF")
                print(f"[✔] File '{filename}' sent to {client_id}.")

            elif command == "CLOSE":
                print(f"[-] Client {client_id} disconnected.")
                break

    except Exception as e:
        print(f"[-] Error handling client {client_id}: {e}")

    finally:
        client_socket.close()


def accept_clients():
    """Accept clients in a separate thread."""
    global server_socket
    while running:
        try:
            client_socket, client_address = server_socket.accept()
            thread = threading.Thread(target=handle_client, args=(client_socket, client_address))
            thread.start()
            client_threads.append(thread)
        except OSError:
            break  # Exit loop if server socket is closed


def start_server():
    """Start the multi-client file transfer server."""
    global server_socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((SERVER_IP, SERVER_PORT))
    server_socket.listen(5)
    print(f"[✔] Server listening on {SERVER_IP}:{SERVER_PORT}")

    accept_thread = threading.Thread(target=accept_clients, daemon=True)
    accept_thread.start()

    try:
        while True:
            pass  # Keep main thread active
    except KeyboardInterrupt:
        print("\n[+] Server shutting down...")
        shutdown_server()


def shutdown_server():
    """Gracefully shutdown the server."""
    global server_socket, running
    running = False  # Stop accept loop

    print("[+] Closing all connections...")
    for thread in client_threads:
        thread.join()  # Wait for all client threads to finish

    if server_socket:
        server_socket.close()
        print("[✔] Server socket closed.")

    sys.exit(0)  # Exit cleanly


if __name__ == "__main__":
    start_server()
